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