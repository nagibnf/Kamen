# Servicos e responsabilidades

## Gateway / UI
- Roteamento por path: /p/<persona_id>
- WebRTC/WS para audio in e video out
- Cria session_id e injeta metadata
- Backpressure quando TTS/Lipsync atrasar

## ASR Service
- Recebe audio PCM 16k
- VAD + faster-whisper streaming
- Emite parciais e finais com timestamps

## LLM Orchestrator
- Recebe texto do ASR + contexto + visao
- Qwen2.5 via TensorRT-LLM
- Streaming de tokens
- Gerencia memoria curta por session_id
- Detecta tool calls e executa via Tool Registry
- Aplica allowlist por persona e timeout por tool

## TTS Service
- Qwen3-TTS streaming + voice cloning
- Fallback: XTTS-v2 ou StyleTTS2
- Saida PCM para Lipsync

## VLM Service
- Qwen2-VL 2B a 1-2 FPS
- Gera resumo curto + tags
- Cache de ultimo resultado por persona

## Lipsync Service
- Wav2Lip com base idle
- ROI cache + resolucao 256/384
- Saida H264 para UI

## Video Output (opcional separado)
- GStreamer pipeline com NVENC/NVDEC
- Mux e entrega via WebRTC/RTSP

## Orchestrator (teste CLI)
- Conecta os servicos via gRPC
- Faz fluxo ASR -> LLM -> TTS -> Lipsync
- Util para validar latencia e formato de dados
