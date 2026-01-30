# Runbook (operacao local)

## Pre-flight
1) Validar GPU e camera.
2) Gerar gRPC stubs (se necessario):
   - ./scripts/gen_proto.sh
3) Exportar PYTHONPATH:
   - export PYTHONPATH=/workspace/src
4) Ativar modo performance quando for benchmark:
   - sudo nvpmodel -m 0
   - sudo jetson_clocks
5) Verificar espaco em /data (modelos e assets).
6) Instalar deps ML (quando for rodar modelos reais):
   - bash /workspace/scripts/install_ml_deps.sh

## Ordem de start (sugestao)
1) ASR
2) LLM
3) TTS
4) VLM
5) Lipsync
6) Gateway/UI

## Servico LLM (stub)
```
python -m avatar.llm_service --port 50052 --persona-id ana --stack /workspace/configs/stack/mock.yaml
```

## Servicos ASR/TTS/VLM/Lipsync (stubs/placeholder)
```
python -m avatar.asr_service --port 50051 --persona-id ana --stack /workspace/configs/stack/mock.yaml
python -m avatar.tts_service --port 50053 --persona-id ana --stack /workspace/configs/stack/mock.yaml
python -m avatar.vlm_service --port 50055 --persona-id ana --stack /workspace/configs/stack/mock.yaml
python -m avatar.lipsync_service --port 50054 --persona-id ana --stack /workspace/configs/stack/mock.yaml
```

## Orchestrator (teste end-to-end)
```
python -m avatar.orchestrator --text "ola mundo" --out-wav /tmp/out.wav --stack /workspace/configs/stack/mock.yaml
```

## Variaveis de ambiente (sugestao)
- AVATAR_CONFIG_STACK=/workspace/configs/stack/default.yaml
- AVATAR_PERSONA_DIR=/workspace/configs/personas
- AVATAR_LOG_DIR=/var/log/avatar
- AVATAR_METRICS_PORT=9090

## Rotas
- UI por persona: /p/<persona_id>
- Reload config: POST /config/reload
- Health: /health

## Observabilidade
- log estruturado por servico (json lines)
- coleta de tegrastats/jtop para GPU/CPU
- latencia por etapa com timestamps

## Recovery rapido
- reiniciar somente o servico com falha
- se TTS ou lipsync atrasar, reduzir FPS ou resolucao via config
