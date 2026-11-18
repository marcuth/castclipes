<h1 align="center">CastClipes</h1>

<p align="center">
  <em>Um funcionário virtual que acompanha as lives dos seus podcasts favoritos e entrega cortes longos e shorts prontos para postar.</em>
</p>

---

## O que é isso?

Podcasts duram horas e os melhores momentos se perdem no meio da conversa. O CastClipes faz o trabalho de um editor de cortes, sozinho e sem parar:

1. **Fica de olho** nas playlists de lives dos canais que você escolheu e espera cada live terminar.
2. **"Assiste"** à live lendo tudo o que foi dito.
3. **Escolhe os melhores momentos**, em dois formatos:
   - **Cortes longos (16:9):** um assunto só, do começo ao fim, de 10 a 40 minutos, com as pausas longas removidas.
   - **Shorts (9:16):** um gancho forte de 20 a 85 segundos, com o rosto de quem fala enquadrado, split-screen quando há dois interlocutores e legenda animada palavra por palavra.
4. **Coloca a moldura** do seu canal por cima (uma para cada formato) e, nos cortes longos, encaixa um vídeo de recado no meio.
5. **Escreve título, descrição e tags**, e monta a capa dos cortes longos.
6. **Publica no YouTube**, espalhando os vídeos em horários distribuídos ao longo do dia.

Tudo isso sem ninguém apertar um botão.

## Como ele decide o que é um bom corte?

Ele usa inteligência artificial como um "olheiro": a IA lê a transcrição da live e **sugere** os melhores momentos. Mas quem tem a última palavra é o código, que segue regras fixas:

- o corte precisa respeitar a duração do formato (longo ou short);
- precisa começar e terminar no fim de uma frase, nunca no meio de uma palavra;
- precisa ter nota boa;
- não pode repetir trechos já usados.

**A IA dá a sugestão, o programa confere se a sugestão faz sentido.** Assim, um palpite errado da IA não vira, sozinho, um vídeo ruim.

## Como o short fica vertical?

Um vídeo de podcast é horizontal, então o programa precisa decidir o que mostrar na tela vertical. Ele analisa o corte, acha os rostos, percebe quem está falando (pelo movimento da boca) e acompanha essa pessoa, com zoom quando ela está longe da câmera. Quando há dois interlocutores, pode dividir a tela em dois blocos empilhados. As legendas aparecem palavra por palavra, e a palavra que está sendo dita acende.

## O que ele não faz

- **Não acompanha a live em tempo real.** Ele espera a transmissão acabar para só então trabalhar.
- **Não sabe quem está falando pela voz.** A transcrição vem sem o nome de quem fala, então ele evita afirmar "fulano disse" quando não tem certeza.
- **Não é perfeito.** A IA erra de vez em quando; revise o que sai antes de soltar no automático (o modo `dry_run` e o envio como privado existem para isso).
- **Não aceita capa própria em Shorts.** O YouTube não permite; a capa vale só para os cortes longos.

## De onde vêm os vídeos?

Os cortes usam o conteúdo das lives originais. Por isso, toda descrição **dá o crédito e o link do episódio original**. Confira a política de cada canal-fonte antes de publicar.

## Começando

```powershell
pip install -e .[dev]          # Whisper local (opcional): .[whisper]
copy .env.example .env         # preencha pelo menos as playlists e a chave de IA
python -m castclipes resolve-channel @canaldopodcast   # descobre o ID da playlist de lives
python -m castclipes process https://www.youtube.com/watch?v=ID --format short   # teste em um vídeo
python -m castclipes watch     # fica monitorando as lives
```

Todas as variáveis estão comentadas no [`.env.example`](.env.example). O programa começa em `PUBLISH_MODE=dry_run`: renderiza tudo em `data/clips/` mas não envia nada ao YouTube.

**Molduras:** coloque um PNG com transparência em `LONG_FRAME_PATH` (1920x1080) e outro em `SHORT_FRAME_PATH` (1080x1920). A moldura é esticada sobre o vídeo inteiro, então use a proporção do formato.

## Quer ver por dentro?

A pasta [`docs/`](docs/README.md) explica o funcionamento em detalhes, assunto por assunto: [o fluxo](docs/pipeline.md), [como os cortes são escolhidos](docs/clip-selection.md), [como o vídeo é editado](docs/video-editing.md), [como os shorts são feitos](docs/shorts.md), [as capas](docs/thumbnails.md) e [a publicação agendada](docs/publishing.md).

## Créditos

O enquadramento por rosto, o split-screen e as legendas dos shorts foram portados do [podcast-clipper](https://github.com/marcuth/podcast-clipper).

## Licença

[MIT](LICENSE)
