<p align="center">
  <img src="docs/images/jaugar-circle.png" alt="Jaguar XIV" width="200">
</p>

<h1 align="center">Jaguar XIV</h1>

<p align="center">
  <em>Um funcionário virtual que assiste às lives por você e entrega os melhores momentos.</em>
</p>

<p align="center">
  📺 <a href="https://www.youtube.com/@jaguarxiv">Canal no YouTube: @jaguarxiv</a>
</p>

---

## O que é isso?

As lives do MBL, do Renan Santos, do Arthur do Val e do Partido Missão duram horas. Quase ninguém tem tempo de assistir a tudo, e os melhores momentos acabam se perdendo no meio da conversa.

O Jaguar XIV é um programa que faz o trabalho de um editor de cortes, sozinho e sem parar:

1. **Fica de olho** nos canais e espera cada live terminar.
2. **"Assiste"** à live lendo tudo o que foi dito.
3. **Escolhe os trechos que valem a pena**: um assunto só, do começo ao fim, com conflito, emoção e uma história que se entende sem ter visto o resto.
4. **Edita o vídeo**: corta o trecho, tira as pausas longas e deixa a fala fluindo, coloca uma moldura com a identidade do canal e encaixa um recado no meio, como um intervalo.
5. **Escreve o título, a descrição e as tags** e monta a imagem de capa.
6. **Publica no YouTube**, espalhando os vídeos em horários distribuídos ao longo do dia.

Tudo isso sem ninguém apertar um botão.

## Como ele decide o que é um bom corte?

Ele usa inteligência artificial como um "olheiro": a IA lê a transcrição da live e **sugere** onde estão os melhores momentos. Mas quem tem a última palavra é o código, que segue regras fixas:

- o corte precisa ter entre 10 e 40 minutos;
- precisa começar e terminar no fim de uma frase, nunca no meio de uma palavra;
- precisa ter nota boa;
- não pode repetir trechos já usados.

A ideia é simples: **a IA dá a sugestão, o programa confere se a sugestão faz sentido.** Assim, um palpite errado da IA não vira, sozinho, um vídeo ruim.

## A capa do vídeo, sem inventar imagem

A imagem de capa (thumbnail) **não é gerada por IA**. O programa olha dezenas de momentos do corte, procura o quadro em que o rosto aparece bem enquadrado, com o fundo mais limpo possível, dá um zoom e escreve por cima uma frase curta e chamativa. É o mesmo trabalho que um editor faria à mão, só que automático.

## O que ele não faz

Honestidade vale mais que propaganda:

- **Não acompanha a live em tempo real.** Ele espera a transmissão acabar para só então trabalhar.
- **Não sabe quem está falando.** A transcrição vem sem o nome de quem fala, então ele evita afirmar "fulano disse" quando não tem certeza.
- **Não é perfeito.** A IA erra de vez em quando, e os títulos e cortes passam por ajustes constantes. É um projeto em evolução.
- **Não é jornalista nem checador de fatos.** Ele recorta o que foi dito nas lives; não verifica nem opina.

## De onde vêm os vídeos?

Os cortes usam o conteúdo das lives originais. Por isso, toda descrição **dá o crédito e o link do vídeo original**: quem quiser ver a conversa completa chega nela com um clique.

## Curiosidades

- Quase tudo roda **no computador de quem opera**, sem depender de serviços de edição de vídeo na nuvem.
- Foi pensado para seguir o estilo dos canais de cortes que já existem: títulos em caixa alta, cortes longos e um assunto por vídeo.
- Ele não tem pressa nem sono: se uma live acaba de madrugada, o corte sai pronto e fica na fila para ser publicado no horário certo.

## Quer ver por dentro?

Para quem tem curiosidade técnica, a pasta [`docs/`](docs/README.md) explica o funcionamento em detalhes, assunto por assunto: [como o fluxo funciona](docs/pipeline.md), [como os cortes são escolhidos](docs/clip-selection.md), [como o vídeo é editado](docs/video-editing.md), [como as capas são feitas](docs/thumbnails.md) e [como a publicação é agendada](docs/publishing.md).

## Aviso

Este é um projeto **independente e não oficial**. O autor, Marcuth, **não tem nenhuma ligação com o MBL ou com o Partido Missão**: é apenas um apoiador.

## Licença

[MIT](LICENSE)
