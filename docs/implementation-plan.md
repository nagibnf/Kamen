# Plano de implementacao (para colocar em producao local)

## Objetivo
Construir um live avatar local com ASR + LLM + TTS + Lipsync + VLM,
rodando em Jetson Thor (JetPack 7.1), com 25-30 FPS e baixa latencia.

## Premissas
- Open source apenas.
- PT-BR.
- Avatar 2D a partir de video real (base idle).
- Qwen para LLM e VLM.
- TTS de alta qualidade (Qwen3-TTS ou fallback XTTS-v2).
- Multi-persona por path (/p/<persona_id>), fase 1 com 1 persona ativa.

## Fase 0 - Ambiente e infraestrutura
1) Validar JetPack 7.1, CUDA, TensorRT, driver e audio/camera.
2) Definir armazenamento para modelos e assets (/data).
3) Definir layout de logs e metrics (/var/log/avatar).
4) Ativar modo performance quando for rodar benchmarks.

Checklist:
- GPU detectada e clocks estaveis.
- Camera e microfone ok.
- Rede interna ok (caso UI em outra maquina).

## Fase 1 - Base do projeto
1) Fixar contratos gRPC (proto/avatar.proto).
2) Fixar configs (configs/stack + configs/personas).
3) Definir padrao de logs (json lines) e ids (persona_id, session_id).
4) Definir padrao de metrics (latencia por etapa).
5) Gerar stubs gRPC (scripts/gen_proto.sh).

Saida:
- Proto e configs versionados.
- Estrutura de pastas pronta para assets.

## Fase 2 - Servicos (MVP)
### ASR
- faster-whisper com VAD (Silero).
- Streaming por chunks (20-40 ms).
- Saida parcial + final com timestamps.
- Servico base: `src/avatar/asr_service.py`
- Para testes rapidos, usar `configs/stack/mock.yaml`

### LLM
- Qwen2.5 7B via TensorRT-LLM.
- Streaming de tokens.
- Prompt com identidade da persona + contexto curto.
- Tool calling (allowlist por persona + retorno ao modelo).
 - Servico base: `src/avatar/llm_service.py`

### TTS
- Qwen3-TTS em modo streaming.
- Voice cloning com sample curto (10-30s).
- Fallback XTTS-v2 se latencia ficar alta.
 - Servico base: `src/avatar/tts_service.py`

### VLM
- Qwen2-VL 2B a 1-2 FPS.
- Resumo curto para injetar no prompt do LLM.
 - Servico base: `src/avatar/vlm_service.py`

### Lipsync
- Wav2Lip com base idle.
- ROI e resolucao 256x256 ou 384x384.
- Saida H264 para reduzir banda.
 - Servico base: `src/avatar/lipsync_service.py`

### Gateway / UI
- Rota /p/<persona_id>.
- WebRTC/WS para audio in e video out.
- Encaminha streams para os servicos via gRPC.

## Fase 3 - Integracao e orquestracao
1) Orquestrador conecta ASR -> LLM -> TTS -> Lipsync.
2) Cache de voice embedding por persona.
3) Contexto do LLM por session_id.
4) Integracao do VLM (1-2 FPS).

## Fase 4 - Otimizacao
- TensorRT para LLM e Lipsync (quando possivel).
- FP16 / INT8 nos modelos maiores.
- Pipeline de video com GStreamer + NVENC/NVDEC.
- Reduzir overhead de copia de memoria (zero-copy).

## Fase 5 - Qualidade e testes
- Benchmarks com metrica de FPS e latencia E2E.
- Testes A/B: Qwen3-TTS vs XTTS-v2.
- Ajuste de resolucao e buffers para atingir 25-30 FPS.

## Fase 6 - Multi-persona (fase 2)
- Carregar 2+ personas simultaneas.
- Medir degradacao de fps e latencia.
- Decidir limite maximo por hardware.

## Definicao de pronto (DoD)
- 25-30 FPS p95 no video final.
- Latencia E2E <= 2.0 s p95.
- TTFT do LLM <= 600 ms p95.
- Voice cloning com qualidade aceitavel (avaliacao manual).
- Sistema estavel por 1h sem memory leak.
