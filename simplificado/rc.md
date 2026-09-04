# INICIO
- crie um arquivo extrai.bat que
-- vai ler app.html
-- ler a tag <musicas>
-- em cada <musica> dentro de <musicas> deve:
--- crie um novo arquivo *.txt dentro da pasta \cifras
--- o nome do arquivo deve ser o conteudo da tag <titulo>
--- o conteudo do arquivo deve ser montado da seguinte forma:
---- Linha com: conteudo da tag <titulo>
---- Linha com: "TOM:" + conteudo da tag <tom>
---- quebra de 2 linhas
---- conteudo dentro de <cifra>
----- conteudo de ntro de <![CDATA[

# NOVA TELA SIMPLIFICADA
- crie um novo arquivo telaCel.html
- esse arquivo irá conter todas as cifras, para isso:
-- crie um inclui.bat que:
--- ao clicar irá recriar em telaCel.html:
---- tag <musicas>
---- tags <musica> com o conteudo de cada arquivo em \cifras
---- primeira linha o nome da música
--- crie um menu alfabético lateral com as iniciais parq eu, quando clicar na inicial, vai para a primeira música da lista que começa com a inicial clicada
- esse arquivo será aberta em celular, logo precisa ser  amigável a visualização


# IDENTIFICAÇÃO DA CIFRA
- no arquivo app.html tem uma função que identifica as cifras no texto
- recrie essa função em telaCel.html
- somente as cifras devem ter a fonte na cor #f60
- a letra das musicas na cor #fff

# TRANSPOR
- no menu lateral
- antes de "A"
- insira "+" para subir meio tom da música
- insira "-" para baixar meio tom da música

# PLAY E PAUSE
- no menu lateral
- antes de "+"
- insira ">" que irá rolar a página sozinha lentamente
-- se clicar de novo em ">" irá aumentar a velocidade em 20%
-- a cada clique aumenta 20%
-- se clicar 6 vezes (acima de 100%) para de rolar
-- clicando mais uma vez depois de parar, volta a rolar na primeira velocidade
- a velocidade e o tom (depois de transposto) fica salvo no cache do navegador

# atualização do git
- em C:\Users\cs385499\PycharmProjects\TelaCifras
- quando executo syncCifraHoliness.bat
- não está atualizando a pasta \simplificado e deve ser atualizada

# CONTROLE DO SCROLL e seleção de música
- remova insira ">" (não ficou bom)
- a velocidade não está mudando como deve
- abaixo do nome de cada música insira um slider que irei ajustar a velocidade para cada música
- o valor do slider para cada música ficará salvo no cache
- na parte inferior da tela o ícone <i class="bi bi-play"></i> em alpha 60%
-- quando clicado irá começar a rolagem e muda para o icone <i class="bi bi-pause"></i>
-- quando clicar em <i class="bi bi-pause"></i> pasa a rolagem e volta o icone <i class="bi bi-play"></i>

# VELOCIDADE DO SCROLL
- só começa a rolar acima de 120%
- deve começar sempre em 0% (parado)
- a cada 5% deve rolar 5px / segundos sendo 100% 100 px / segundos

# SELEÇÃO DAS MÚSICAS
- é possivel clicar sobre as músicas
- clicando ela muda para a cor #f60
- clicando novamente volta para a cor original
- quando na cor #f60 entendemos que ela está selecionada
- ao selecionar, pelo menos, uma música deve:
-- aparecer o icone <i class="bi bi-funnel"></i> em alpha 60% ao lado esquerdo do icone <i class="bi bi-play"></i>
-- clicando em <i class="bi bi-funnel"></i> deve:
--- filtrar mostrando apenas as músicas selecionadas na ordem em que foram selecionadas
-- deve aparecer o ícone <i class="bi bi-x"></i> em alpha 60% ao lado direito do icone <i class="bi bi-play"></i>
-- clicando em <i class="bi bi-x"></i> remove os filtros (músicas selecionadas) voltando ao original
-- músicas selecionadas devem ficar salvas no cache do navegador

# AJUSTE NA VISUALIZAÇÃO
- o objetivo é visualizar cifras na tela do celular
- entretanto algumas músicas possuem uma linha longa (maior que a largura da tela)
- quero uma função que quebre a linha da cifra (e não a linha normal do texto)
- por exemplo, a música "A Lua Que Eu Te Dei":

 
 
A9                 A/G                  F#m7            D9
Posso te falar dos sonhos das flores de como a cidade mudou
A9                A/G            F#m7          D9
Posso te falar do medo  do meu desejo  do meu amor
A9      A9/C#   D9                  B/D#       A/E
Posso falar  da tarde que cai e aos poucos deixa ver
   C#7(9+)  F#m7         F7M       A9/E
No céu    a lua   que um dia eu te dei
 


- deve quebrar assim:

A9                 A/G    
Posso te falar dos sonhos 
              F#m7            D9
das flores de como a cidade mudou
A9                A/G   
Posso te falar do medo  
         F#m7          D9
do meu desejo  do meu amor
A9      A9/C#   D9    
Posso falar  da tarde 
              B/D#       A/E
que cai e aos poucos deixa ver
   C#7(9+)  F#m7  
No céu    a lua   
       F7M       A9/E
que um dia eu te dei

- ou seja:
-- identifica mais ou menos o meio da linha e escolhe o inicio de uma palavra
-- quebra tanto a linha da cifra quando a linha da letra na mesma posição
-- mantem a posição da cifra exatamente na mesma posição sobre a letra
-- deve ocorrer quando identificar que a linha é maior que a tela
--- quando a linha não for maior que a tela, não deve quebrar
-- analise é feita pode linha e não na música, ou seja:
--- a mesma música pode ter linhas quebradas e outras não

# AJUSTE ROLAGEM
- na rolagem definimos que 1% corsponde a 1px/só
- quero mudar, a cada 1% corresponde a 0.5px/s ou seja, 2% é 1px/segundo

# ANALISE DE TECNOLOGIA
- não implemente nada
- quero avaliar se há uma tecnologia que:
-- vou usar a telaCel.html no celular
-- quero ter outro arquivo html no computador
-- conectar o celular no computador via bluethoth
-- quero que o que a musica da tela do celular apareça também no computador, apenas a letra
-- no computador posso ter um arquivo com todas as letras
-- mas precisa mostrar o trecho exato que está na tela do celular na tela do computador
-- para que pessoas possam ler e cantar junto na igreja
-- nao havalie, me de alternativas de abordagens

# INDICAÇÃO NO MEU LATERAL
- no meu lateral, a letra que estiver com a musica (inicial do nome) na tela, a letra do menu deve ficar #f60
- substitua o botão "+" do menu lateral por <i class="bi bi-plus"></i> a esquerda de <i class="bi bi-play">, mas 25% menor que <i class="bi bi-play"> e com mesmo alpha
- substitua o botão "-" do menu lateral por <i class="bi bi-dash"></i> a direita de <i class="bi bi-play">, mas 25% menor que <i class="bi bi-play"> e com mesmo alpha
- para ganhar espaço em tela, remova <h1>Cifras</h1>

# DICIONARIO DE ACORDES
- em app.html tem uma função que identifica as notas musicais dos acordes
- entenda essa função e:
-- quando clicar em cima de um acorde na letra da música, deve aparecer um modal em alpha 55% somente com as notas musicais do acorde clicado
-- não marque os acordes como elementos clicaveis (tipo link) não mude a formatação
-- apenas quando clicar ele deve mostrar esse modal

# AJUSTES DE INTERFACE
- em letras.html
-- remover id="titulo"
-- devemos aproveitar o máximo da tela com a letra da música
-- linha com "TOM:" não deve aparecer em letras.html

- em telaCel.html
-- quando a cifra tiver a tag <intro> o que estiver dentro dessa tag deve:
--- aparecer telaCel.html com a letra color: #bbb
--- aparecer telaCel.html com a cifra color: #0ff
- em letras.html
-- as linhas das letras de telaCel.html que estiverem dentro de <intro> deve:
--- aparecer "<i class="bi bi-music-note"></i> <i class="bi bi-music-note"></i> <i class="bi bi-music-note"></i>" em cada linha dentro de <intro>
--- <intro> indica que é introdução, a letra é apenas um guia para quem está tocando e por isso não deve aparecer no letras.html
--- não precisa aparecer literalmente "<intro>" em telaCel.html e nem em letras.html

- em telaCel.html
- quando etiver com músicas selecionadas e filtradas e play ativado
- ao trocar de música deve
-- esperar 5 segundos até começar a nova música
--- durante esse tempo de espera em letras.html deve aparecer o titulo da música centralizado na tela
--- ao começar a rolar o titulo some e a letra começa a subir conforme telaCel.html
-- se em algum momento o play for pausado
--- em letras.html deve aparecer o titulo da música centralizado na tela
--- ao começar a rolar (play ativado) o titulo some e a letra começa a subir conforme telaCel.html

- em telaCel.html
- quando play estiver ativado deve aparecer:
-- posicionado na lateral direita, sobre o menu alfabético posicionados um abaixo do outro e no tamanho de class="bi bi-dash"
--- icone <i class="bi bi-music-note"></i> que se clicado deve reduzir a taxa de rolagem em 5px/segundo
--- icone <i class="bi bi-music-note-beamed"></i></i> que se clicado deve aumentar a taxa de rolagem em 5px/segundo
-- deve ser no mesmo padrão dos demais ícones, com mesmo alpha (pode usar mesma classe)
-- esses ícones só aparecem enquanto play estiver ativo e rolagem acontecendo, se pausar o play os ícones desaparecem
-- ele irá alterar somente a música atual (que está na tela)
- quando traspor a cifra em id="transpor-mais-btn" ou id="transpor-menos-btn"
-- também deve transpor o tom indicado na linha com "TOM:"

- implemente sem quebrar nada, na duvida pergunte

# ALTERAÇÃO DA TAXA DE ROLAGEM
- testando aqui vi que precisamos mudar esse trecho:
--- icone <i class="bi bi-music-note"></i> que se clicado deve reduzir a taxa de rolagem em 1px/segundo
--- icone <i class="bi bi-music-note-beamed"></i></i> que se clicado deve aumentar a taxa de rolagem em 1px/segundo

# AJUSTE DA VELOCIDADE
- quando troca música a parada de 5 segundos está funcionando muito bem
- o ajuste de velocidade entre as músicas deveria acontecer no mesmo momento
- mas quando a segunda música já aparece embaixo da tela, a velocidade considerada passa a ser ela mesmo ainda estando tocando a anterior
- o ajuste é simples, a troca da velocidade deve ocorrer após a parada dos 5 segundos, que está acontecendo no momento correto

# DUVIDA SOBRE O ESP
- ontem eu fiz upload dos arquivos em \simplificado\nodeMCU através da IDE do arquino, baixando e instalando bibliotecas
- não implemente nada, quero apenas analisar uma alternativas
- é possível construir um *.bat que após eu conectar o nodemcu na porta usb, executar e ele atualizar os arquivos no módulo?

# COMPARTILHAR
- criar um botão ao lado direito de class="bi bi-x" com o ícone <i class="bi bi-share"></i> que irá aparecer somente se tiver pelo menos uma música selecionada
- ele irá criar uma url para compartilhar que:
-- deve enviar na url o id das músicas selecionadas
-- deve enviar na url o valor de class="velocidade-valor" de cada música selecionada
-- quando o destinatário abrir o link já abrirá com o mesmo filtro das músicas e com os valores da velocidade para cada uma
- se o destinatário clicar em class="bi bi-x", mostrará todas as músicas, exatamente como funciona hoje
- aqui a questão é apenas criar a url
-- provavelmente terá que criar um sistema de id para as músicas para poder enviar como GET
# DOWNLOAD
- botão <i class="bi bi-cloud-download"></i> ao lado esquerdo de class="bi bi-funnel"
- esse botão deve fazer download de todo o arquivo html

# NÃO FUNCIONOU
- em letras.html
-- as linhas das letras de telaCel.html que estiverem dentro de <intro> deve:
--- aparecer "<i class="bi bi-music-note"></i> <i class="bi bi-music-note"></i> <i class="bi bi-music-note"></i>" em letras.html PARA cada linha dentro de <intro> em telaCel.html 
- reforçando que deve aparecer "<i class="bi bi-music-note"></i> <i class="bi bi-music-note"></i> <i class="bi bi-music-note"></i>" somente em letras.html, substituindo as linhas dentro de <intro>

# BLQUEIO DE TELA
- a funcionalidade e não blpquear avtela do celular quando play ativo parou de funcionar, antes funcionava bem em  telaCel.html

# NÃO HÁ SINCRONIA
- ainda não entendi o motivo, mas as vezes funciona e as vezes não
- quando não funciona, não aparece nada no monitor serial
- parece que mesmo estando no mesmo wifi (CifrasIgreja) telaCel.html não se conecta

# ICONES
- icones não aparecem no index pq está offline
- sendo assim, substitua apenas em index.html:
-- class="bi bi-music-note" por unicode dec &#9834;
-- class="bi bi-music-note-beamed" por unicode dec &#9835;
-- class="bi bi-play" por unicode dec &#9655;
-- class="bi bi-pause" por unicode dec &#9208;
-- class="bi bi-plus" por unicode dec &#10750;
-- class="bi bi-dash" por unicode dec &#10751;
-- class="bi bi-cloud-download" por unicode dec &#129123;
-- class="bi bi-funnel" por unicode dec &#10032;
-- class="bi bi-share" por unicode dec &#128279;


# AJUSTE SINCRONIA
- notei que quando a música está no topo de telaCel.html (rolando para cima quase sumindo) a mesma linha está embaixo, surgindo em letras.html
- esse comportamento prejudica acompanhar
- quando a linha estiver sumindo no topo de telaCel.html a linha correspondente também precisa estar sumindo no topo em letras.html

# GRUPOS
- inclui.bat inclui as cifras que estão na pasta \cifras
- quero separar essas cifras por grupos
- dentro da pasta cifras terão subpastas, o nome dessas pastas serão os grupos
- como acessar os grupos em telaCel.html e \nodeMCU\data\index.html
-- dentro de id="nav-alfabeto", o último caractere de ser <i class="bi bi-node-plus-fill"></i> (icone de grupo) no mesmo tamanho da fonte em id="nav-alfabeto"
-- ao clicar nesse ícone de grupo:
--- mostra uma div oculta no topo da página
--- dentro dessa div terão botões no mesmo estilo dos demais class="botao-circular", mas não precisa ser circular
--- o texto desses botões serão os nomes das pastas em \cifras
--- ao clicar no botão irá mostrar as cifras dentro dessa pasta, atualizando id="nav-alfabeto"
--- ao clicar no ícone do grupo irá ocultar novamente a div que contem os botões
- deve ficar salvo no cache o último botão clicado e a lista de musicas selecionadas
- não quebre nada do que já está funcionando
- se houverem musicas fora de grupo (subpastas) elas serão mostradas se nenhum grupo estiver selecionado
- ao selecionar um grupo apenas as músicas daquele grupo serão mostradas

# BUG QUANDO COMPARTILHAR
- testando ontem a funcionalidade de compartilhar (class="bi bi-share")
- gera um link no qual envio por whats app
- mas quando abre no telefone de destino o link não funciona o play (class="bi bi-play")
- só funciona se remover da url as variaveis GET
- não quebre nada, analise onde está o bug e corrija

# ICONES
- icones não aparecem no index pq está offline
- sendo assim, substitua quando estiver offline em index.html e telaCel.html:
-- class="bi bi-share" por unicode dec &#9430;







