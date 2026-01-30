# Dependencias (ML / runtime)

Este repo inclui apenas o scaffold. Para rodar os modelos reais, instale:

## Base
- Python 3.10+
- CUDA + cuDNN + TensorRT (JetPack 7.1)
- GStreamer (NVENC/NVDEC)

## ASR
- faster-whisper (CTranslate2 + CUDA)
- numpy

## LLM
- TensorRT-LLM (recomendado) ou transformers + torch
- Qwen2.5 checkpoints (7B/14B)

## TTS
- Qwen3-TTS (preferencial) ou Coqui TTS (XTTS-v2)
- torch + torchaudio

## VLM
- Qwen2-VL (2B/7B) via runtime compativel (transformers/TensorRT)

## Lipsync
- Wav2Lip (PyTorch)
- opencv-python

## Observacoes
- Em Jetson, prefira builds NVIDIA para torch/TensorRT.
- Se o backend nao estiver instalado, os servicos usam mock.
