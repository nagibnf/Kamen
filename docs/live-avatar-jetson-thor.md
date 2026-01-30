# Pesquisa e arquitetura: Live Avatar local (ASR + LLM + TTS + lipsync)

## Objetivo
Construir um assistente de voz em portugues, totalmente local, que:
- reconhece fala (ASR) em tempo real
- responde com LLM
- sintetiza voz (TTS)
- faz lipsync em video em tempo real
- usa camera para "ver" o ambiente via VLM
- roda em uma Jetson Thor com JetPack 7.1, explorando GPU ao maximo

## Requisitos atuais (conforme pedido)
- avatar a partir de video gravado com pessoa real (2D)
- 25-30 fps, com aparencia de video real
- foco em menor latencia possivel
- PT-BR
- somente open source
- LLM: Qwen
- VLM: Qwen-VL
- TTS com qualidade superior ao Piper (avaliar Qwen3-TTS e alternativas)
- arquitetura que permita trocar modelos para testes
- clonagem de voz desejavel
- multiplas personas, cada uma com URL/interface separada

## Resumo de conclusoes (curto)
- Nao existe um stack open source unico que resolva tudo "out of the box".
- O caminho mais realista e integrar componentes open source por etapa.
- Para Jetson, priorize modelos menores + quantizacao + TensorRT / CUDA.
- Para video real 30-35 fps, Wav2Lip (2D) e o caminho mais pratico,
  mas exige otimizacao (ROI, TensorRT, fp16, pipeline de video).
- Para TTS de maior qualidade, Qwen3-TTS e uma aposta promissora,
  com fallback para XTTS-v2 ou StyleTTS2 se latencia for alta.

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
- **Qwen2.5 7B** (bom em PT, bom custo/qualidade).
- **Qwen2.5 14B** (melhor qualidade, mais pesado).
- **Llama 3.1 8B** (fallback geral).
Recomendacao: **TensorRT-LLM + Qwen2.5 7B (4-bit)** para menor latencia.

### 4) VLM (vision + linguagem)
Para "ver" o ambiente via camera e gerar descricoes ou respostas.
Opcoes open source:
- **Qwen2-VL** (2B/7B): bom, mas pesado.
- **LLaVA 1.6**: popular, mas pesado.
- **Phi-3.5-Vision**: pequeno e bom, mas depende de suporte.
- **Moondream2**: leve, bom para consultas simples.
Recomendacao: **Qwen2-VL 2B** se couber na GPU com 1-2 FPS.
Se ficar pesado, usar Moondream2 como fallback leve.

### 5) TTS (text to speech)
Opcoes open source:
- **Qwen3-TTS** (QwenLM): alta qualidade, foco em streaming e voice
  design/cloning (validar latencia e PT-BR na Jetson).
- **Coqui TTS / XTTS-v2**: qualidade alta, multilanguage, pesado.
- **StyleTTS2**: qualidade alta, pode exigir adaptacao de voz.
- **Piper** (Rhasspy): muito rapido, CPU-friendly, vozes PT-BR.
- **Mimic3**: leve, qualidade media.
Recomendacao (para este projeto):
- Primario: **Qwen3-TTS** (se entregar latencia e PT-BR).
- Fallback de qualidade: **XTTS-v2** (tem voice cloning) ou **StyleTTS2**.
- Piper apenas para debug/benchmark de latencia.

### 5b) Pesquisa rapida: Qwen3-TTS
- Repo oficial: **QwenLM/Qwen3-TTS** (open source).
- Existem nodes ComfyUI para Qwen3-TTS (indicacao de modelos 0.6B/1.7B).
- Acoes pendentes: validar licenca, requisitos GPU e performance real
  em Jetson Thor (fp16/int8), suporte efetivo a PT-BR e voice cloning.

### 5c) Clonagem de voz (PT-BR)
Opcoes open source com qualidade alta:
- **Qwen3-TTS**: se o voice cloning estiver estavel.
- **XTTS-v2**: clonagem com amostra curta, bom equilibrio.
- **StyleTTS2**: precisa pipeline de adaptacao, mais trabalho.
Recomendacao:
- manter um banco de "voice profiles" por persona (wav curto + embedding).

### 6) Lipsync / Avatar em video (video real)
Opcoes open source:
- **Wav2Lip**: padrao de fato, bom e relativamente simples.
  - Com GPU, pode chegar perto de tempo real em 256x256.
- **SadTalker**: qualidade alta, mas nao e tempo real.
- **Avatarify + FOMM**: live, mas qualidade menor para boca.
- **Rhubarb**: lipsync 2D (desenho), leve mas limitado.
Recomendacao: **Wav2Lip** para 2D real-time.

Notas para 25-30 fps com video real:
- usar video base (idle) com face frontal e pouca variacao de luz
- pre-processar face crop/align e usar so ROI de boca
- 256x256 ou 384x384 para equilibrar qualidade x latencia
- TensorRT / TorchScript + fp16 para acelerar
- pipeline de video com NVDEC/NVENC (GStreamer) e zero-copy

### 6b) Preparacao do video base (avatar real)
- gravar 5-10 minutos com rosto frontal e iluminacao constante
- gerar "idle loop" (trecho curto em loop) para quando nao fala
- salvar landmarks e bounding boxes para acelerar inferencia

## Stacks integradas existentes
Nao ha um "stack completo" open source com ASR+LLM+TTS+Lipsync+VLM.
O mais proximo e juntar:
- **OpenVoiceOS / Mycroft** (assistente) + ASR/TTS custom
- **Wav2Lip** para video
Logo, a integracao custom e o caminho mais seguro.

## Stack recomendada (open source, baixa latencia)

### MVP realista (latencia minima + 30-35 fps)
- VAD: Silero VAD
- ASR: faster-whisper (distil-large-v3) CUDA
- LLM: TensorRT-LLM + Qwen2.5 7B (4-bit)
- TTS: Qwen3-TTS (streaming) ou XTTS-v2 (fallback)
- Lipsync: Wav2Lip (256x256, ROI)
- VLM: Qwen2-VL 2B (1-2 FPS)

### Evolucao (mais qualidade)
- ASR: whisper large-v3
- LLM: Qwen2.5 14B (se couber)
- TTS: Qwen3-TTS (modelo maior) ou StyleTTS2 com voz ajustada
- VLM: Qwen2-VL 7B (se couber)
- Lipsync: Wav2Lip com resolucao maior se mantiver fps alvo

## Pipeline proposto (dados e processos)

```
Mic -> VAD -> ASR (stream) -> texto
texto + contexto + memoria + visao -> LLM (stream)
tokens -> TTS (stream) -> audio
audio + video base (idle) -> Lipsync -> video frames
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

## Arquitetura para troca rapida de modelos
Objetivo: permitir testes rapidos sem reescrever o pipeline.
- padronizar contrato de entrada/saida por etapa (ASR/LLM/TTS/VLM)
- cada servico expor API simples: `/health`, `/config`, `/stream`
- selecionar modelos via arquivo de configuracao (YAML/JSON)
- manter "adapter" por backend (TensorRT, PyTorch, ONNX)

Exemplo de config (conceitual):
```
asr:
  backend: faster_whisper
  model: distil-large-v3
llm:
  backend: tensorrt_llm
  model: qwen2.5-7b
tts:
  backend: qwen3_tts
  model: qwen3-tts-0.6b
vlm:
  backend: qwen2_vl
  model: qwen2-vl-2b
lipsync:
  backend: wav2lip
  model: wav2lip_gan.pth
```

## Multi-persona (URLs diferentes)
Objetivo: varias personas com URL/interface separada e recursos isolados.

### Estrategia recomendada
- **Persona Registry**: catalogo de personas (id, nome, voz, video base).
- **Config por persona** (YAML/JSON): define modelos e assets.
- **Routing por URL**: `https://host/p/<persona_id>` ou subdominio.
- **Sessao por persona**: o contexto do LLM e o cache de voz ficam isolados.

### Assets por persona
- video base (idle) + landmarks/bboxes
- voice sample curto (10-30s) para clonagem
- prompt/identidade para LLM

### Exemplo de config por persona (conceitual)
```
persona:
  id: ana
  name: "Ana"
  base_video: /data/avatars/ana/idle.mp4
  voice_sample: /data/voices/ana_ref.wav
  system_prompt: "Voce e a Ana, amigavel e objetiva."
stack:
  asr: { backend: faster_whisper, model: distil-large-v3 }
  llm: { backend: tensorrt_llm, model: qwen2.5-7b }
  tts: { backend: qwen3_tts, model: qwen3-tts-0.6b }
  vlm: { backend: qwen2_vl, model: qwen2-vl-2b }
  lipsync: { backend: wav2lip, model: wav2lip_gan.pth }
```

### Observacoes
- Para muitas personas simultaneas, compartilhar ASR/LLM como servico
  central e manter TTS/Lipsync por persona quando necessario.
- Salvar embeddings de voz para reduzir latencia de clonagem.

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
- **TTS lento**: ajustar streaming, reduzir modelo, usar XTTS-v2/StyleTTS2.
- **Lipsync pesado**: reduzir resolucao, usar ROI e batch pequeno.
- **VLM pesado**: reduzir FPS e usar Qwen2-VL 2B.
- **Video 30-35 fps**: otimizar pipeline (NVDEC/NVENC, zero-copy).

## Proximos passos recomendados
- Definir alvo de latencia e qualidade (SLA interno).
- Validar Qwen3-TTS (licenca, PT-BR, latencia, streaming).
- Validar Qwen2-VL (2B) com 1-2 FPS.
- Escolher 1 stack MVP e validar no Jetson real.
- Coletar metricas (RTF, latencia, uso de GPU/CPU).
- Ajustar modelos e batch size ate atingir tempo real.
- Criar 1-2 personas piloto (video base + voice sample) e medir fps.
