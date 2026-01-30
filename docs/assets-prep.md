# Preparacao de assets (video e voz)

## Video base (persona)
Objetivo: criar um video idle realista para o lipsync.

Checklist de gravacao:
- camera fixa, iluminacao constante
- rosto frontal, pouca variacao de pose
- resolucao 1080p ou 4k (sera reduzido no pipeline)
- 5-10 minutos de material bruto

Passos:
1) Selecionar trecho "idle" com expressao neutra.
2) Cortar um loop de 5-10s sem movimentos bruscos.
3) Gerar landmarks e ROI (boca).
4) Salvar base_idle.mp4 e caches em /data/personas/<id>.

Exemplos (comandos a ajustar):
- cortar trecho:
  - ffmpeg -i input.mp4 -ss 00:01:10 -t 00:00:08 -c copy base_idle.mp4
- reduzir resolucao:
  - ffmpeg -i base_idle.mp4 -vf scale=512:-1 base_idle_512.mp4

## Voz (voice cloning)
Objetivo: criar um voice sample curto para clonagem.

Checklist:
- gravar 10-30s em ambiente silencioso
- sem musica ou ruido de fundo
- sample rate 22k-24k, mono

Passos:
1) Normalizar volume.
2) Remover silcios longos.
3) Salvar ref.wav na pasta da persona.

Observacao:
- Gerar embedding de voz na primeira execucao e salvar no disco.
