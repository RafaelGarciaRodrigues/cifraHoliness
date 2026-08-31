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

