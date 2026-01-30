# Pesquisa e arquitetura: Live Avatar local (ASR + LLM + TTS + lipsync)

## Objetivo
Construir um assistente de voz em portugues, totalmente local, que:
- reconhece fala (ASR) em tempo real
- responde com LLM
- sintetiza voz (TTS)
- faz lipsync em video em tempo real
- usa camera para "ver" o ambiente via VLM
- roda em uma Jetson Thor com JetPack 7.1, explorando GPU ao maximo

## Resumo de conclusoes (curto)
- Nao existe um stack open source unico que resolva tudo "out of the box".
- O caminho mais realista e integrar componentes open source por etapa.
- Para Jetson, priorize modelos pequenos + quantizacao + TensorRT / CUDA.
- O lipsync em tempo real mais pratico hoje e Wav2Lip (2D) ou Audio2Face
  (nao open source, mas local) caso aceite 3D.
- Para PT-BR, Whisper (ASR) e Piper ou XTTS (TTS) funcionam bem.

## Pesquisa de componentes open source por etapa

### 1) VAD (Voice Activity Detection)
Usado para reduzir latencia e custo do ASR.
- **Silero VAD** (PyTorch): leve, bom para streaming.
- **WebRTC VAD** (C): muito rapido e estavel, qualidade ok.
Recomendacao: Silero VAD (melhor tradeoff qualidade/uso).

### 2) ASR (Automatic Speech Recognition)
Opcoes open source, com bom suporte a portugues:
- **faster-whisper** (CTranslate2 + CUDA): rapido, streaming via chunks.
  - modelos: `medium`, `large-v3`, `distil-large-v3` (menor latencia).
- **whisper.cpp** (ggml): roda bem em CPU e GPU, streaming simples.
- **NVIDIA NeMo**: bom para treino, mas mais pesado para deploy.
Recomendacao: **faster-whisper + CUDA** com `distil-large-v3` (MVP),
subir para `large-v3` se a GPU permitir latencia baixa.

### 3) LLM (texto -> resposta)
Opcoes open source para rodar local:
- **Llama.cpp** (CUDA): simples e estavel, mas menos eficiente que TRT.
- **TensorRT-LLM** (NVIDIA): melhor desempenho em Jetson.
- **vLLM**: alto throughput, mas pode ser pesado no Jetson.
Modelos sugeridos:
- **Llama 3.1 8B** (bom geral, precisa quantizacao 4-bit/8-bit).
- **Qwen2.5 7B** (forte em raciocinio, bom em PT).
- **Mistral 7B** (bom custo/qualidade).
Recomendacao: **TensorRT-LLM + Llama 3.1 8B ou Qwen2.5 7B**.

### 4) VLM (vision + linguagem)
Para "ver" o ambiente via camera e gerar descricoes ou respostas.
Opcoes open source:
- **LLaVA 1.6**: popular, mas pesado.
- **Phi-3.5-Vision**: pequeno e bom, mas depende de suporte.
- **Qwen2-VL**: bom, mas pesado.
- **Moondream2**: leve, bom para consultas simples.
Recomendacao: **Moondream2** (MVP leve) ou **Phi-3.5-Vision**
se a GPU suportar. Rodar a 1-2 FPS para reduzir carga.

### 5) TTS (text to speech)
Opcoes open source:
- **Piper** (Rhasspy): muito rapido, CPU-friendly, vozes PT-BR.
- **Coqui TTS / XTTS-v2**: qualidade alta, mas pesado.
- **Mimic3**: leve, qualidade media.
Recomendacao:
- MVP de baixa latencia: **Piper (pt_BR)**.
- Se quiser mais naturalidade e tiver GPU sobrando: **XTTS-v2**.

### 6) Lipsync / Avatar em video
Opcoes open source:
- **Wav2Lip**: padrao de fato, bom e relativamente simples.
  - Com GPU, pode chegar perto de tempo real em 256x256 / 25fps.
- **SadTalker**: qualidade alta, mas nao e tempo real.
- **Avatarify + FOMM**: live, mas qualidade menor para boca.
- **Rhubarb**: lipsync 2D (desenho), leve mas limitado.
Opcao nao-open-source (mas local e robusta):
- **NVIDIA Audio2Face**: excelente para 3D e tempo real.
Recomendacao: **Wav2Lip** para 2D real-time.

## Stacks integradas existentes
Nao ha um "stack completo" open source com ASR+LLM+TTS+Lipsync+VLM.
O mais proximo e juntar:
- **OpenVoiceOS / Mycroft** (assistente) + ASR/TTS custom
- **Wav2Lip** para video
Logo, a integracao custom e o caminho mais seguro.

## Stack recomendada (MVP + evolucao)

### MVP (foco em latencia)
- VAD: Silero VAD
- ASR: faster-whisper (distil-large-v3) CUDA
- LLM: TensorRT-LLM + Llama 3.1 8B (4-bit)
- TTS: Piper (pt_BR)
- Lipsync: Wav2Lip (256x256)
- VLM: Moondream2 (1-2 FPS)

### Evolucao (qualidade maior)
- ASR: whisper large-v3
- LLM: Qwen2.5 14B (se couber), ou Llama 3.1 70B remoto/local maior
- TTS: XTTS-v2
- VLM: Phi-3.5-Vision ou Qwen2-VL
- Lipsync: Wav2Lip + refinamento (GFPGAN) se custo permitir

## Pipeline proposto (dados e processos)

```
Mic -> VAD -> ASR (stream) -> texto
texto + contexto + memoria + visao -> LLM (stream)
tokens -> TTS (stream) -> audio
audio -> Lipsync -> video frames
Camera -> VLM (1-2 fps) -> "resumo do que ve"
```

### Latencia alvo (estimativa)
- VAD: 100-200 ms
- ASR parcial: 300-700 ms
- LLM: 200-800 ms para primeiros tokens
- TTS: 200-500 ms para audio inicial
- Lipsync buffer: 200-400 ms
Latencia total percebida: 1.0 a 2.5 s (ajustavel).

## Arquitetura de processos (recomendado)
Use processos separados com filas (ZeroMQ / Redis / gRPC):
1. **Audio Ingest**: captura audio, aplica VAD, envia chunks.
2. **ASR Service**: streaming ASR e textos parciais.
3. **LLM Orchestrator**: prompt + memoria + tool use + VLM.
4. **TTS Service**: gera audio em streaming.
5. **Lipsync Service**: Wav2Lip ou pipeline de avatar.
6. **Video Output**: gstreamer + NVENC para RTSP/WebRTC.
7. **Vision Service**: captura camera, roda VLM, envia resumo.

## Uso de GPU na Jetson Thor
- Prefira **TensorRT-LLM** e **TensorRT** para maximo desempenho.
- Use quantizacao 4-bit/8-bit para LLM e VLM.
- Ative modo performance (nvpmodel) e clocks fixos (jetson_clocks).
- Use GStreamer + NVENC/NVDEC para pipeline de video.

## Plano de implementacao (passos)
1. **Audio->ASR**: Mic + VAD + faster-whisper streaming.
2. **ASR->LLM**: prompt baseline, memoria curta.
3. **LLM->TTS**: Piper com voz PT-BR, playback local.
4. **TTS->Lipsync**: Wav2Lip com video base (idle).
5. **Camera->VLM**: Moondream2, 1-2 fps.
6. **Integracao completa**: orquestrador + latencia otimizada.

## Riscos e mitigacoes
- **Latencia alta**: reduzir tamanho de modelos, usar quantizacao.
- **Qualidade baixa de voz**: migrar Piper -> XTTS-v2.
- **Lipsync pesado**: reduzir resolucao, usar batch pequeno.
- **VLM pesado**: reduzir FPS e usar modelo menor.

## Proximos passos recomendados
- Definir alvo de latencia e qualidade (SLA interno).
- Escolher 1 stack MVP e validar no Jetson real.
- Coletar metricas (RTF, latencia, uso de GPU/CPU).
- Ajustar modelos e batch size ate atingir tempo real.
