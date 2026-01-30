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
- multiplas personas, cada uma com URL/interface separada (path)
- fase inicial: uma persona ativa por vez

## Resumo de conclusoes (curto)
- Nao existe um stack open source unico que resolva tudo "out of the box".
- O caminho mais realista e integrar componentes open source por etapa.
- Para Jetson, priorize modelos menores + quantizacao + TensorRT / CUDA.
- Para video real 25-30 fps, Wav2Lip (2D) e o caminho mais pratico,
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

### 3b) Function tools (LLM)
Sim, faz sentido usar tools para acionar funcoes durante a conversa:
- controle de camera, acao de sistema, consultas locais, etc.
- manter **allowlist** por persona para seguranca.
- executar tools no **LLM Orchestrator** (nao no modelo).

Fluxo sugerido:
1) LLM gera um "tool call" (nome + args).
2) Orchestrator valida allowlist e executa tool.
3) Resultado volta para o LLM continuar a resposta.

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
- integracao Wav2Lip pode gerar MP4 (H264) como saida

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

### MVP realista (latencia minima + 25-30 fps)
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
services:
  asr: localhost:50051
  llm: localhost:50052
  tts: localhost:50053
  lipsync: localhost:50054
  vlm: localhost:50055
asr:
  backend: faster_whisper
  model: distil-large-v3
llm:
  backend: tensorrt_llm
  model: qwen2.5-7b
tts:
  backend: qwen3_tts
  model: qwen3-tts-0.6b
  cmd_template: "qwen3-tts --text \"{text}\" --out \"{out_wav}\" --voice \"{voice_sample}\""
vlm:
  backend: qwen2_vl
  model: qwen2-vl-2b
lipsync:
  backend: wav2lip
  model: wav2lip_gan.pth
  repo_path: /opt/wav2lip
tools:
  enabled: true
  allowlist: ["get_time", "list_personas"]
```

## Blueprint de APIs (contratos)
Objetivo: contratos claros para trocar modelos e manter latencia baixa.
Recomendacao: gRPC streaming entre servicos e WebRTC/WS para UI.

### Campos comuns (todos os servicos)
- `persona_id`: id da persona (ex: "ana")
- `session_id`: id da conversa/sessao
- `request_id`: id unico por chamada
- `ts_ms`: timestamp

### ASR Service (streaming)
- **Entrada**: stream de `AudioChunk`
  - `pcm_s16le`, `sample_rate=16000`, `channels=1`
- **Saida**: stream de `AsrPartial`
  - `text`, `is_final`, `start_ms`, `end_ms`, `confidence`
Endpoint (conceitual): `rpc StreamAsr(stream AudioChunk) returns (stream AsrPartial)`

### LLM Orchestrator (streaming)
- **Entrada**: `LlmRequest`
  - `text`, `context`, `vision_summary`, `persona_profile`
- **Saida**: stream de `LlmEvent`
  - `token`, `tool_call`, `tool_result`
Endpoint: `rpc StreamLlm(LlmRequest) returns (stream LlmEvent)`

Notas:
- O Orchestrator e responsavel por detectar tool calls e executar.
- Manter allowlist por persona e limites de tempo por tool.

### TTS Service (streaming + voice cloning)
- **Entrada**: `TtsRequest`
  - `text`, `voice_profile_id` ou `voice_sample_path`
  - `speed`, `temperature`, `top_p`
- **Saida**: stream de `AudioChunk` (pcm)
Endpoint: `rpc StreamTts(TtsRequest) returns (stream AudioChunk)`

### Lipsync Service
- **Entrada**: `LipsyncRequest`
  - `audio_stream` (pcm), `base_video_path`, `roi_cache`
- **Saida**: stream de `VideoFrame` (raw) ou `H264Packet`
Endpoint: `rpc StreamLipsync(stream AudioChunk) returns (stream VideoFrame)`

### VLM Service
- **Entrada**: `ImageFrame` (RGB/BGR) ou camera id
- **Saida**: `VisionSummary` (texto curto + tags)
Endpoint: `rpc AnalyzeFrame(ImageFrame) returns (VisionSummary)`

### UI / Gateway
- **Path por persona**: `/p/<persona_id>`
- UI abre WebRTC/WS para:
  - envio de audio do mic
  - recepcao de audio TTS
  - recepcao de video lipsync (H264)
  - exibicao de legenda (ASR/LLM)

### Config/Hot swap
- `POST /config/reload` por servico
- `GET /config/current` para debug

## gRPC Proto (draft)
Objetivo: definir mensagens minimas para streaming.

```
syntax = "proto3";
package avatar;

message Meta {
  string persona_id = 1;
  string session_id = 2;
  string request_id = 3;
  int64 ts_ms = 4;
}

message AudioChunk {
  Meta meta = 1;
  bytes pcm_s16le = 2;
  int32 sample_rate = 3; // 16000
  int32 channels = 4;    // 1
}

message AsrPartial {
  Meta meta = 1;
  string text = 2;
  bool is_final = 3;
  int64 start_ms = 4;
  int64 end_ms = 5;
  float confidence = 6;
}

message LlmRequest {
  Meta meta = 1;
  string text = 2;
  string context = 3;
  string vision_summary = 4;
  string persona_profile = 5;
}

message LlmToken {
  Meta meta = 1;
  string token = 2;
  bool is_final = 3;
  int64 latency_ms = 4;
}

message ToolCall {
  Meta meta = 1;
  string name = 2;
  string args_json = 3;
}

message ToolResult {
  Meta meta = 1;
  string name = 2;
  string result_json = 3;
  bool ok = 4;
  string error = 5;
}

message LlmEvent {
  oneof event {
    LlmToken token = 1;
    ToolCall tool_call = 2;
    ToolResult tool_result = 3;
  }
}

message TtsRequest {
  Meta meta = 1;
  string text = 2;
  string voice_profile_id = 3;
  string voice_sample_path = 4;
  float speed = 5;
  float temperature = 6;
  float top_p = 7;
}

message VideoFrame {
  Meta meta = 1;
  bytes data = 2;      // raw RGB or H264 packet
  int32 width = 3;
  int32 height = 4;
  string format = 5;   // "rgb24" or "h264"
}

message VisionSummary {
  Meta meta = 1;
  string text = 2;
  repeated string tags = 3;
}

service AsrService {
  rpc StreamAsr(stream AudioChunk) returns (stream AsrPartial);
}
service LlmService {
  rpc StreamLlm(LlmRequest) returns (stream LlmEvent);
}
service TtsService {
  rpc StreamTts(TtsRequest) returns (stream AudioChunk);
}
service LipsyncService {
  rpc StreamLipsync(stream AudioChunk) returns (stream VideoFrame);
}
service VlmService {
  rpc AnalyzeFrame(VideoFrame) returns (VisionSummary);
}
```

Notas:
- Para lipsync, o `base_video_path` pode ser definido via config por persona.
- Para video, enviar H264 direto reduz largura de banda.

## Diagrama de deploy (logico)

```
[Browser UI /p/<persona>]
   |  mic (WS/WebRTC)
   v
[Gateway/API] --grpc--> [ASR] --text--> [LLM] --tokens--> [TTS]
   |                                   ^             |
   |                                   |             v
   |                           [VLM] <-+         [Lipsync]
   |                                                |
   +------------------- H264/WebRTC --------------- +
```

Componentes sugeridos:
- **Gateway**: autentica, roteia por persona, agrega streams.
- **ASR/LLM/TTS/VLM/Lipsync**: processos separados, GPU dedicada.
- **Video Output**: pode ser integrado no Lipsync ou separado via GStreamer.

## Fluxo de dados por persona (com cache)
Objetivo: baixa latencia e isolamento de estado.

1. **Session start**
   - carregar config da persona
   - carregar video base + landmarks + ROI cache
   - carregar voice profile (embedding ou sample)
2. **Streaming**
   - mic -> ASR -> texto parcial/final
   - texto + contexto + vision -> LLM (tokens)
   - tokens -> TTS (audio stream)
   - audio + base video -> lipsync -> video stream
3. **Caches**
   - **voice embedding** por persona (persistente)
   - **LLM context** por session_id (memoria curta)
   - **ROI cache** por video base (persistente)
4. **Fallbacks**
   - se VLM lento, reduzir fps ou desligar
   - se TTS lento, trocar modelo via config

## Persona Registry (schema + estrutura)
Objetivo: padronizar assets por persona para troca rapida.

### Estrutura de pastas (sugestao)
```
/data/personas/
  ana/
    persona.yaml
    video/
      base_idle.mp4
      landmarks.json
      roi_cache.json
    voice/
      ref.wav
      embedding.bin
```

### persona.yaml (exemplo)
```
id: ana
name: "Ana"
language: "pt-BR"
base_video: /data/personas/ana/video/base_idle.mp4
landmarks: /data/personas/ana/video/landmarks.json
roi_cache: /data/personas/ana/video/roi_cache.json
voice_sample: /data/personas/ana/voice/ref.wav
voice_embedding: /data/personas/ana/voice/embedding.bin
system_prompt: "Voce e a Ana, amigavel e objetiva."
stack:
  asr: { backend: faster_whisper, model: distil-large-v3 }
  llm: { backend: tensorrt_llm, model: qwen2.5-7b }
  tts: { backend: qwen3_tts, model: qwen3-tts-0.6b }
  vlm: { backend: qwen2_vl, model: qwen2-vl-2b }
  lipsync: { backend: wav2lip, model: wav2lip_gan.pth }
  tools:
    allowlist: ["get_time", "list_personas"]
```

## Cache e politicas de eviccao
Objetivo: manter baixa latencia e estabilidade.

### O que cachear
- **Voice embedding** por persona (persistente no disco + em RAM)
- **LLM context** por session_id (memoria curta)
- **ROI cache** por video base (persistente)
- **Model weights** (mantidos carregados quando possivel)

### Politicas recomendadas
- **LLM context**: TTL por sessao (ex: 15-30 min) + limite de tokens
- **Voice embedding**: LRU em RAM com fallback em disco
- **ROI cache**: sem eviccao (pequeno e estatico)
- **Model swap**: hot reload com janela de aquecimento

## Roteamento e isolamento de sessao
Objetivo: separar personas e conversas sem vazamento de contexto.

### Regras
- cada request carrega `persona_id` e `session_id`
- `persona_id` define assets e modelos usados
- `session_id` define memoria curta do LLM e estado da conversa

### Gateway (path routing)
- rota: `/p/<persona_id>`
- cria session_id no primeiro acesso
- injeta headers para servicos internos (gRPC metadata)

### Limites e protecoes
- limitar 1 persona ativa (fase 1)
- fila por persona para evitar overload
- backpressure no ASR/LLM quando TTS ou lipsync atrasar

## Multi-persona (URLs diferentes)
Objetivo: varias personas com URL/interface separada e recursos isolados.

### Estrategia recomendada
- **Persona Registry**: catalogo de personas (id, nome, voz, video base).
- **Config por persona** (YAML/JSON): define modelos e assets.
- **Routing por URL**: `https://host/p/<persona_id>` (path).
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
- Fase 1: rodar **uma persona por vez** para maximizar performance.
- Fase 2: ativar varias personas simultaneas para medir capacidade.
- Para varias personas simultaneas, compartilhar ASR/LLM como servico
  central e manter TTS/Lipsync por persona quando necessario.
- Salvar embeddings de voz para reduzir latencia de clonagem.

## Plano de benchmark (performance e qualidade)
Objetivo: medir se o sistema cumpre 25-30 fps e baixa latencia.

### Metricas chave
- **FPS** do video final (media e p95)
- **Latencia E2E** (speech->video): p50/p95
- **TTFT** do LLM (time-to-first-token)
- **RTF ASR** e **RTF TTS**
- **Uso de GPU/CPU** (tegrastats/jtop)
- **VRAM** e **bandwidth**
- **Qualidade**: WER (ASR) e MOS subjetivo (TTS)

### Cenarios
1. **Baseline**: 1 persona, VLM OFF, 30s de fala gravada.
2. **VLM ON**: 1-2 FPS, medir impacto em fps e latencia.
3. **Voice cloning**: comparar Qwen3-TTS vs XTTS-v2.
4. **Stress**: 2+ personas simultaneas (fase 2).

### Procedimento
- Rodar cada cenario 3x, coletar medias e p95.
- Exportar logs para CSV (timestamp, stage, latency_ms).
- Fixar clocks (jetson_clocks) e modo performance.

### Criterios de sucesso
- Video >= 25 FPS (p95)
- Latencia E2E <= 2.0 s (p95) no MVP
- TTFT LLM <= 600 ms (p95)

## Uso de GPU na Jetson Thor
- Prefira **TensorRT-LLM** e **TensorRT** para maximo desempenho.
- Use quantizacao 4-bit/8-bit para LLM e VLM.
- Ative modo performance (nvpmodel) e clocks fixos (jetson_clocks).
- Use GStreamer + NVENC/NVDEC para pipeline de video.

## Plano de implementacao (passos)
1. **Audio->ASR**: Mic + VAD + faster-whisper streaming.
2. **ASR->LLM**: prompt baseline, memoria curta.
3. **LLM->TTS**: Qwen3-TTS (ou XTTS-v2), playback local.
4. **TTS->Lipsync**: Wav2Lip com video base (idle).
5. **Camera->VLM**: Qwen2-VL 2B, 1-2 fps.
6. **Integracao completa**: orquestrador + latencia otimizada.

## Riscos e mitigacoes
- **Latencia alta**: reduzir tamanho de modelos, usar quantizacao.
- **TTS lento**: ajustar streaming, reduzir modelo, usar XTTS-v2/StyleTTS2.
- **Lipsync pesado**: reduzir resolucao, usar ROI e batch pequeno.
- **VLM pesado**: reduzir FPS e usar Qwen2-VL 2B.
- **Video 25-30 fps**: otimizar pipeline (NVDEC/NVENC, zero-copy).

## Proximos passos recomendados
- Definir alvo de latencia e qualidade (SLA interno).
- Validar Qwen3-TTS (licenca, PT-BR, latencia, streaming).
- Validar Qwen2-VL (2B) com 1-2 FPS.
- Escolher 1 stack MVP e validar no Jetson real.
- Coletar metricas (RTF, latencia, uso de GPU/CPU).
- Ajustar modelos e batch size ate atingir tempo real.
- Criar 1-2 personas piloto (video base + voice sample) e medir fps.
