# Especificação Técnica: Pipeline Automatizado de Transcrição Musical em Python

Este documento define a especificação técnica detalhada para a construção de uma ferramenta em Python capaz de receber um arquivo de áudio musical, isolar um instrumento específico (como o solo de guitarra ou teclado) utilizando Inteligência Artificial, identificar deterministicamente as notas musicais geradas e exportar a sequência cronológica em um arquivo de texto.

o arquivo se chamara solo.py e será executado pelo cmd pelo comando: python solo.py

---

## 1. Arquitetura do Sistema e Fluxo de Dados

O pipeline opera em três camadas distintas com abordagens de processamento híbridas:

```
[ Áudio Completo (.mp3/.wav) ]
              │
              ▼
   (Fase 1: Probabilística)  --> Separação de Fontes com IA (Demucs)
              │
              ▼
    [ Áudio do Solo (.wav) ]
              │
              ▼
   (Fase 2: Determinística)  --> Extração de Pitch e Tempo (Librosa + pYIN)
              │
              ▼
 [ Tratamento de Dados (Filtro)]--> Remoção de oscilações e mapeamento temporal
              │
              ▼
   [ Arquivo de Saída (.txt) ] --> Sequência cronológica estruturada
```

1. **Camada de Separação de Fontes (Probabilística):** Separação cega de fontes (BSS) utilizando redes neurais convolucionais e transformadores para decompor a onda misturada em subfaixas limpas.
2. **Camada de Análise de Frequência (Determinística):** Aplicação de modelagem probabilística de caminhos ocultos de Markov combinada com autocorrelação matemática (algoritmo pYIN) para rastrear a frequência fundamental ($f_0$) sobre o tempo.
3. **Camada de Estruturação:** Mapeamento de frequências Hz em notação científica internacional e vinculação aos carimbos de tempo (timestamps) absolutos.

---

## 2. Pré-requisitos e Dependências do Sistema

Para o funcionamento correto das bibliotecas Python, o sistema operacional necessita de decodificadores de áudio nativos.

### 2.1. Dependência do Sistema Operacional (FFmpeg)
O **FFmpeg** é obrigatório para que as bibliotecas Python consigam ler, converter e fatiar arquivos compactados (como MP3, AAC, FLAC).

*   **Linux (Ubuntu/Debian):**
    ```bash
    sudo apt update && sudo apt install ffmpeg -y
    ```
*   **macOS (via Homebrew):**
    ```bash
    brew install ffmpeg
    ```
*   **Windows:**
    Recomenda-se instalar via gerenciador de pacotes `winget`:
    ```cmd
    winget install "FFmpeg (Essentials Build)"
    ```
    *Nota: Certifique-se de que o executável do FFmpeg esteja adicionado ao PATH global do sistema.*

### 2.2. Ambiente Python e Bibliotecas (requirements.txt)
O projeto requer o **Python 3.8 ou superior**. As dependências de bibliotecas devem ser consolidadas no arquivo `requirements.txt`:

```text
# requirements.txt
demucs>=4.0.0
librosa>=0.10.0
numpy>=1.22.0
scipy>=1.8.0
soundfile>=0.12.1
```

*   **Instalação dos pacotes:**
    ```bash
    pip install -r requirements.txt
    ```

---

## 3. Especificação do Passo a Passo da Implementação

### Passo 1: Ingestão de Áudio e Inicialização do Ambiente
O script deve verificar a existência do arquivo de entrada e criar de forma dinâmica a estrutura de pastas temporárias para evitar conflitos de cache ou sobrescritas acidentais de execuções anteriores.
deve decodificar o audio dentro da pasta \audio se tiver mais de um informa e para de rodar para que o usuario escolha qual ele quer decodificar

### Passo 2: Separação Espectral via Inteligência Artificial
Nesta etapa, o áudio unificado passa pela separação do modelo **HTDemucs** (Hybrid Transformer Demucs). 
*   **Modelo recomendado:** `htdemucs` (padrão de 4 canais).
*   **Outputs gerados:** O modelo dividirá a música estéreo em quatro arquivos independentes com amostragem de 44.1kHz no formato WAV:
    1. `vocals.wav` (Voz e harmônicos vocais)
    2. `drums.wav` (Elementos percussivos e transientes de impacto)
    3. `bass.wav` (Frequências sub-graves e linhas de contrabaixo)
    4. `other.wav` (Instrumentos harmônicos e melódicos: guitarras, sintetizadores, pianos, solos)
*   **Ação do Script:** Isolar e carregar estritamente a trilha correspondente a `other.wav` (ou a trilha onde reside o solo desejado).

### Passo 3: Rastreamento de Pitch Monofônico (pYIN)
Para garantir a precisão milimétrica que as extensões de navegador perdem, o script utilizará o algoritmo matemático **pYIN (Probabilistic YIN)** via `librosa`.
*   **Processamento:** O áudio isolado é fragmentado em blocos de tempo (*frames*). Para cada bloco, o algoritmo calcula a autocorrelação da onda para encontrar o período de repetição mais estável.
*   **Parâmetros críticos de filtragem:**
    *   `fmin` (Mínimo de frequência): Configurado em `librosa.note_to_hz('C2')` (~65 Hz) para evitar captar resíduos remanescentes de baixo.
    *   `fmax` (Máximo de frequência): Configurado em `librosa.note_to_hz('C7')` (~2093 Hz) para ignorar harmônicos agudos e ruídos brancos de altíssima frequência.
*   **Saída do algoritmo:** Um array contendo o valor numérico exato em Hertz ($f_0$) ou `NaN` para trechos de silêncio ou pausas.

### Passo 4: Mapeamento Temporal e Conversão de Notas
Como a frequência flutua milimetricamente durante um vibrato ou bend de uma guitarra, o algoritmo de tratamento de dados precisa filtrar essas micro-variações em tempo real:
1. Converter os índices dos blocos analíticos (*frames*) de volta para segundos através da função `librosa.frames_to_time()`.
2. Mapear as frequências em Hertz válidas para notas usando `librosa.hz_to_note()`.
3. **Filtro de Estabilização:** Criar um acumulador temporal. Uma nota só deve ser registrada se permanecer estável pelo tempo de duração mínimo estipulado (ex: 50 milissegundos). Se a extensão ler mudanças rápidas demais (ruído residual), o script descarta e mantém o pitch predominante.

### Passo 5: Exportação Estruturada do Arquivo de Texto
A saída final deve priorizar a legibilidade para o músico que irá reproduzir o solo. O arquivo de texto gerado deve estruturar as informações relacionando o tempo exato com a nota.

---

## 4. Estrutura do Arquivo de Saída Esperado

O formato do arquivo texto gerado pelo script obedecerá ao seguinte padrão cronológico estrito:

```text
==================================================
TRANSCRIÇÃO DE SOLO AUTOMATIZADA
Arquivo de Origem: solo_guitarra_faixa1.mp3
Instrumento Alvo: Outros / Solo
==================================================

[00:02.14] -> E4
[00:02.55] -> G4
[00:03.10] -> A4
[00:03.85] -> B4
[00:04.20] -> A4
[00:04.60] -> G4
[00:05.12] -> E4
[00:07.40] -> D4
[00:08.05] -> E4

==================================================
Fim da transcrição de notas.
```

Salva o arquivo txt na pasta \tablaturas com o mesmo nome do audio que originou a analise


---

## 5. Código-Fonte de Referência do Script

```python
import os
import subprocess
import librosa
import numpy as np

def formatar_tempo(segundos):
    minutos = int(segundos // 60)
    segs = int(segundos % 60)
    milisegundos = int((segundos - int(segundos)) * 100)
    return f"{minutos:02d}:{segs:02d}.{milisegundos:02d}"

def executar_pipeline(caminho_musica, pasta_saida="output_pipeline", alvo="other"):
    if not os.path.exists(caminho_musica):
        print(f"Erro: Arquivo {caminho_musica} não encontrado.")
        return

    # 1. Separação de Fontes (IA)
    print("[1/4] Iniciando separação com Inteligência Artificial (Demucs)...")
    comando = f"demucs -o {pasta_saida} \"{caminho_musica}\""
    subprocess.run(comando, shell=True, check=True)
    
    nome_base = os.path.splitext(os.path.basename(caminho_musica))[0]
    caminho_solo = os.path.join(pasta_saida, "htdemucs", nome_base, f"{alvo}.wav")
    
    if not os.path.exists(caminho_solo):
        print("Erro crítico: Falha ao localizar o arquivo de áudio isolado.")
        return

    # 2. Processamento e Análise de Áudio (Determinístico)
    print("[2/4] Carregando o áudio isolado e executando algoritmo pYIN...")
    y, sr = librosa.load(caminho_solo, sr=None)
    
    f0, voiced_flag, voiced_probs = librosa.pyin(
        y, 
        fmin=librosa.note_to_hz('C2'), 
        fmax=librosa.note_to_hz('C7'), 
        sr=sr
    )
    
    # 3. Mapeamento de Notas e Timestamps
    print("[3/4] Mapeando frequências matemáticas para notas musicais...")
    tempos = librosa.frames_to_time(range(len(f0)), sr=sr)
    
    linhas_transcricao = []
    ultima_nota = None
    
    for i, f em enumerate(f0):
        if not np.isnan(f):
            nota_atual = librosa.hz_to_note(f)
            
            # Filtro básico de repetitividade e ruído instantâneo
            if nota_atual != ultima_nota:
                tempo_formatado = formatar_tempo(tempos[i])
                linhas_transcricao.append(f"[{tempo_formatado}] -> {nota_atual}")
                ultima_nota = nota_atual

    # 4. Geração do Arquivo de Texto Final
    print("[4/4] Gravando relatório final...")
    nome_txt = f"transcricao_{nome_base}.txt"
    with open(nome_txt, "w", encoding="utf-8") as f_out:
        f_out.write("==================================================\n")
        f_out.write("TRANSCRIÇÃO DE SOLO AUTOMATIZADA\n")
        f_out.write(f"Arquivo de Origem: {os.path.basename(caminho_musica)}\n")
        f_out.write(f"Instrumento Alvo: {alvo.upper()}\n")
        f_out.write("==================================================\n\n")
        f_out.write("\n".join(linhas_transcricao))
        f_out.write("\n\n==================================================\n")
        f_out.write("Fim da transcrição de notas.\n")
        
    print(f"Pipeline finalizado com sucesso! Arquivo gerado: {nome_txt}")

if __name__ == "__main__":
    # Exemplo de chamada:
    # executar_pipeline("musica_teste.mp3")
    pass
```

# AJUSTES
- RODOU E NO FINAL SALVOU O ARQUIVO EM \tablaturas
- pelo que percebi ele separa as faixas da música
- quero que crie dentro da pasta \faixas mais uma pasta com o nome do arquivo de audio (sem a extensão)
- dentro dessa pasta ele salva as faixas de audio separadas para que eu possa escutar e avaliar em alta qualidade
- vi que a tablatura salva possui dois campos, o tempo em que a nota foi identificada e a nota
- sendo assim é possivel criar um arquivo html com o mesmo nome do aruivo de audio que:
-- terá um javascript e irá usar a informação do tempo para criar uma linha de tempo e quando der o play irá soar a nota daquele tempo
-- deve permitir navegar na linha de tempo, para frent e para trás
-- deve permitir acelerar e deruzir a velocidade
-- deve permitir pausar e seguir
- salve esse arquivo dentro da pasta \tablaturas com o mesmo no do arquivo de audio com a extensão html

# MELHORIA
- a separação da voz funcionou bem
- sobre o arquivo html:
-- quando as notas vão avançando e mudando as linhas, a barra de rolagem vertical da tela inteira desce, impedindo de ver a linha do tempo
-- a barra de rolagem não deve ser afetada, eu que comando ela e onde a tela estará 
-- em algum lugar mostrar o tom da música (para isso o script precisa identificar)

- sobre as notas
-- não consegui identificar de qual faixa identificou as notas, pois está diferente de todas
-- as notas não correspondem a música
-- não conheço o script em detalhes mas acredito que deve ter como melhorar o resultado
-- quero sempre pegar as notas do instrumento que está tocando o solo
-- se for possível, fazer uma trilha do solo e outra dos acordes
--- a trilha dos acordes não precisa ser tocada como mid, apenas mostrada na tela, no momento em que o acorde é tocado, na linha de tempo
-- inserir uma opção de transpor todas as notas e os acordes, pois em um momento vou usar para eu poder tocar

# SEPARAÇÃO
- a separação usando os elementos 'Notas exibidas e tocadas' e 'Tocar junto a faixa separada (áudio real)' ajudaram a identificar qual instrumento está gerando as notas
- mas ajudou a identificar uma falha
- a musica usada como teste possui um acordeon, que pode ser interpretado como orgão ou piano e isso não é problema (mas se conseguir identificar acordeon será um benefício pois esse é o instrumento que eu toco)
- entretanto na mesma música ele identifica o acordeon como piano/teclado e em outros trechos da música como Outros instrumentos
- identifiquei isso porque escutando junto a faixa, em certo momento a de piano para de tocar, e quando vou para outros intrumentos ela aparece
- nesse ponto, há possibilidade de otimizar o modelo?

- Tocar faixas juntas
-- quero que o elemento id="faixa" seja um multiselect
-- posso selecionar mais de uma faixa para serem tocadas juntas

# REMODELAR FRONT END
- insira id em todos os elementos, para que possamos melhor expecificar
- esses ids podem ser hexadecimais aleatórios

## Implementado (30/09/2026)
- acordeon: o Demucs não tem faixa de acordeon (retreinar exigiria dataset próprio); ele o reparte entre piano e outros
-- criada a faixa combinada acordeon.wav = piano + outros; usada como candidata ao solo no lugar das duas
- faixa: virou lista de caixas de marcar; várias faixas tocam juntas, sincronizadas ao player
- ids: elementos fixos com hex aleatório (6 caracteres, começando por letra); elementos gerados com ids previsíveis (faixa-piano, listaNotas-0, letra-3...)

# LETRA, INTERFACE ÚNICA E CADASTRO
- perguntas respondidas: é possível transcrever a letra e acompanhá-la na tela por frase; o painel pode ser editável
- implementado:
-- letra: faster-whisper transcreve a faixa vocals.wav (modelo medium, português, tempo por palavra), dividida em frases
-- letra salva em \letras\<id> - <nome>.txt no formato [início - fim] frase; se o arquivo existir, nunca é sobrescrito
-- cada áudio recebe um id = 8 hex do SHA-256 do arquivo (mesmo áudio, mesmo id, mesmo se renomeado)
-- pastas: faixas\<id>\, dados\<id>.json (notas, acordes, tom), letras\, musicas.db (SQLite)
-- faixas já separadas são reaproveitadas (Demucs só roda de novo se a pasta faixas\<id> for apagada)
-- um único player: python app.py abre http://127.0.0.1:8765 (servidor local, só biblioteca padrão do Python)
-- aba Player: player anterior + painel de letra vertical (frase atual destacada, palavra a palavra, rola só dentro do painel)
--- modo Editar: corrigir texto, ±0,1 s, marcar início/fim no tempo atual, dividir, juntar, inserir, excluir
--- rascunho guardado no navegador; "Salvar letra" (Ctrl+S) grava direto em \letras
-- aba Biblioteca: tabela do musicas.db com filtros, ordenação e edição na célula
--- editáveis: favorito, título, artista, categoria, status, meu tom (transposição), tags, observações
-- preferências por música ficam no banco (transposição, velocidade, faixas marcadas, fonte das notas, timbre)
- o player HTML por música (modelo_player.html e tablaturas\*.html) foi substituído por interface.html


# AJUSTES
- há algum problema de encoder nas letras, estão saindo assim: "Das trÃªs bocas ao ItÃº quantas lÃ©guas que terÃ¡"
- há algum bug na seleção das faixas para tocar junto id="faixa"
-- quando desmarco uma qualquer ela fica muda (ok) mas quando marco ela de novo ela não tocada
-- mas se eu desmarcar outra, a que não estava tocando, volta a tocar

- em id="ab97f5" mostre todas as músicas, inclusive as que não foram processadas
- para as não processadas, insira um botão na linha para processar
-- essa ação substitui python solo.py "NOME DA MUSICA.webm"

- crie um arquivo SOLO.bat que irá chamar python app.py e depois abre em http://127.0.0.1:8765.

## Implementado (ajustes acima)
- letra com acentos quebrados: causada por um teste do assistente (texto lido em cp1252 e regravado); o código do app estava correto
-- letras\2970503b - LUIZ MARENCO.txt restaurada (22 de 22 frases iguais à transcrição original)
- faixas: remarcar uma faixa durante a reprodução deixava ela muda
-- causa: a correção de sincronia reposicionava a faixa ainda carregando a cada quadro, reiniciando o carregamento
-- agora só corrige faixas prontas, e marcar uma faixa não interrompe as que já tocam
- Biblioteca mostra todos os áudios da pasta \audio; os não processados têm o botão "⚙ Processar"
-- roda o solo.py pelo servidor (fila, uma música por vez) e mostra a etapa atual; ao terminar, a música entra na lista
-- a lista é recarregada ao abrir a aba Biblioteca (não precisa mais de F5); filtro de status "Não processadas"
- SOLO.bat: abre o servidor (janela "Tela de Solos - servidor") e o navegador em http://127.0.0.1:8765
-- se a interface já estiver aberta, o app.py avisa que a porta está em uso em vez de abrir outra

# ERROS
- na música 'Deus de Amor'
- em certo momento, algumas faixas pararam de tocar sem desmarcar eus respectivos type="checkbox". Mas depois repeti a execução e isso não aconteceu. Erro intermitente
- a letr saiu com alguns erros, corrigido o erro o script não conseguiu mais identificar onde está a posição a ser tocada (palavra)
- é possível usar um modelo mais robusto para a captação da letra mesmo que demore mais?
- depois que eu corrigir a letra, dá para fazer uma "combinação forçada" como você havia sugerido antes, na sua ideia de pre carregar a letra? Um botão que faça isso ou algo similar
- ressalto que pre carregar a letra é uma opção mas exige eu escrever ela antes, e corrigir é mais fácil, por isso neguei a sua ideia
- ao lado de id="btnFaixasNenhuma" quero um botão "Marcar Todas"
- ao lado de id="f3e12e" quero um <i class="bi bi-volume-mute"></i> que ira mutar as notas sintetizadas e se mutadas mostrará <i class="bi bi-volume-up"></i> para voltar a tocar
- quero dois novos botões em id="b13d76"
-- esses botões devem mostrar a extensão vocal da música, ou seja
-- o primeiro deve ter o label interno dele a menor nota cantada da música, considerando somente a trilha de voz
-- ao clicar nesse botão, um midi que pareca voz falando a letra "A" deve soar a nota por 5 segundos tendo fade in e fade output_pipeline
-- outro botão com a nova máxima (mais alta) da voz com o mesmo comportamento, ao clicar soa midi "A" por 5 segundo com fade in e out na nota
## Implementado (erros acima)
- faixas parando de forma intermitente: faixa que travava esperando dados voltava atrasada, saltava, travava de novo...
-- atraso pequeno agora é corrigido acelerando/desacelerando levemente a faixa (sem salto)
-- salto só para atraso grande, no máximo a cada 2,5 s, já descontando o tempo de carregamento medido
- posição das palavras depois de corrigir a letra:
-- na hora: palavras que continuam iguais herdam o tempo da transcrição original; as trocadas ficam entre as vizinhas
-- botão "🎯 Alinhar ao áudio" (combinação forçada): o Whisper recebe o texto corrigido e acha o tempo de cada palavra
--- ajusta também início/fim de cada frase; a versão anterior da letra vai para letras\anteriores
--- usa o openai-whisper 'medium' (já instalado; modelo baixado na 1ª vez)
- modelo mais robusto: transcrição passa a usar o Whisper large-v3 (~3 GB, mais lento, mais preciso)
-- botão "↻ Transcrever de novo" refaz a letra de uma música já processada (cópia da anterior em letras\anteriores)
- "Marcar todas" ao lado de "Desmarcar todas"
- botão mudo (bi-volume-mute / bi-volume-up) nas notas sintetizadas; fica salvo por música
- extensão vocal: dois botões com a nota mais grave e a mais aguda da faixa de voz (ignora 2% extremos, erros comuns)
-- clique: voz sintética cantando "A" por 5 s com fade in/out (clique de novo para parar); acompanha a transposição


# ERRO EXTENSÃO VOCAL
- na musica Thiago Brado - Noites Traiçoeiras (Clássicos da Igreja) - Thiago Brado (youtube)
- mostra que a menor nota é E3 e a maior G#5
-- acredito que a G#5 esteja errada provavelmente pegou de algum instrumento e não da faixa de voz. precisa sempre pegar da faixa da voz

# MELHORIA NA EDIÇÃO
- mesmo com o modelo de trascrição mais robusto temos problemas com a eltra e com o alinhamento
- sendo assim, para tudo ficar mais leve quero:
-- voltar para a versão mais leve do  Whisper
-- remova o botão e as funções atreladas em "Alinhar ao áudio" e a "Transcrever de novo"
-- no modo edição, destaque os botões '⏱ início'
-- no modo edição, destaque os botões '✂ dividir'
-- quer uma funcionaildade de copiar varias frases (pode ser clicando e segurando o shift) e poder colar em um determinada parte da música
-- quando pressionar + depois, o tempo deve ser o mesmo que está na linha do tempo (atualmente preciso apertar depois em inicio)
-- pode remover os botões (e as funções no script correlacionadas) que não serão usados no modo edição:
--- -0,1 s
--- +0,1 s
--- + Frase no tempo atual
## Implementado (melhoria na edição)
- Whisper voltou para o 'medium' (mais leve)
- removidos "🎯 Alinhar ao áudio" e "↻ Transcrever de novo" (botões, rotas do app.py e funções do letra.py)
-- mantido: palavras não alteradas numa frase corrigida herdam o tempo da transcrição original
- modo edição:
-- "⏱ início" e "✂ dividir" destacados
-- "＋ depois" cria a frase no tempo atual da linha do tempo
-- removidos "−0,1 s", "+0,1 s" e "＋ Frase no tempo atual" (com letra vazia aparece "＋ primeira frase aqui")
-- copiar/colar: caixa de seleção em cada frase (Shift+clique marca um intervalo); "⧉ Copiar" (Ctrl+C) e
   "📋 Colar no tempo atual" (Ctrl+V) insere as frases a partir da linha do tempo mantendo os intervalos entre elas

# DISTORÇÃO
- o grid no modo edição ficou desalinhado
- acredito que o problema está nos tamanho dos botões, vamos trocar por icones sem texto:
-- Editar: <i class="bi bi-pencil"></i>
-- Salvar letra: <i class="bi bi-floppy2-fill"></i>
-- Descartar alterações: <i class="bi bi-x-circle"></i>
-- Concluir edição: <i class="bi bi-floppy2-fill"></i> (aqui eu quero uma mudança, sempre que conlcuir já salva)
-- Copiar: <i class="bi bi-copy"></i>
-- Colar no tempo atual: <i class="bi bi-clipboard-check"></i> (esse botão só aparece se antes clicar em copiar)

- ja nas no grid das linhas no modo edição em cada class="frase atual":
-- ter duas divs de linha
--- uma com: class="selecaoFrase", class="tempoFrase" e o input da frase (esse deve ocupar o máximo espaço disponível da linha
--- linha de baixo com class="acoesFrase"
## Implementado (distorção)
- botões da letra viraram ícones sem texto (nome na dica ao passar o mouse): editar, salvar, descartar, copiar, colar
-- "Concluir edição" (bi-floppy2-fill) sempre salva antes de sair; se o salvamento falhar, continua editando
-- "Colar" só aparece depois de copiar
- linha da frase no modo edição em duas divs: em cima seleção + tempo + texto (ocupa o resto); embaixo as ações

# QUALIDADE DOS AUDIO FAIXAS
- foi um requisito os audios das faixas serem de alta qualidade
- ao escutar ele está com "estalinhos" e distorções tipicas de baixa qualidade
- escutando apenas o arquibp wav na pasta, não parece ter um pouco mais de qualidade
- acredito que afalha possa estar na execução do audio na interface
- avaliar uma abordagem melhor, para reproduzir a melhor qualidade

# VIDEO PARA KARAOKE
- quero exportar um video para KARAOKE
- terá apenas as faixas selecionadas em id="faixa"
- o fundo do video será todo preto
- letras brancas
- a letra da música sobe no video
- a frase em evidência (na lnha de tempo) deve aparecer no centro do video na cor brancas
- as frases que já passaram ficam em cima (subindo) na cor cinza
- as frases que ainda não foram cantadas ficam embaixo na cor cinza
- em alguns casos pode ser que eu queira fazer um video de apenas um trecho da música, nesse caso:
-- abaixo de id="barra" ter outra barra para delimitar o corte
-- deve possibilitar arrastar o inicio e o final
-- formar o video somente da parte que está dentro da barra delimitada
-- deve salvar o video com dentro de uma pasta \videos com o nome no formato [ARTISTA] - [TÍTULO].mp4
-- criar o botão 'Criar vídeo' em id="b13d76"

## Implementado (qualidade das faixas e vídeo para karaokê)
- estalinhos/distorção vinham da reprodução, não dos WAV:
-- a correção de sincronia acelerava/desacelerava as faixas (liga o "esticador de tempo" do navegador, que estala) e dava saltos
-- faixas somadas podiam passar do volume máximo (clipping), ex.: acordeon + piano
- nova reprodução: em 1× as faixas marcadas são decodificadas para a memória e tocadas pela Web Audio,
  todas no mesmo relógio das notas sintetizadas: sincronia exata, sem correção nenhuma, som igual ao WAV
-- em outra velocidade continua o <audio> do navegador (único jeito de manter a afinação), sem ajustes de velocidade
-- limitador na saída (faixas + notas), começo/parada das faixas com fade de 10 ms (sem estalo)
-- tela e marcações (⏱ início/fim, ＋ depois, colar) descontam a latência de saída: batem com o que se ouve
- vídeo para karaokê: botão "🎬 Criar vídeo" (video.py, na fila do servidor)
-- áudio: só as faixas marcadas (mistura + limitador), AAC 256 kbps; vídeo 1280×720, 30 qps
-- fundo preto; frase atual branca e maior no centro; já cantadas em cima e próximas embaixo em cinza; rolagem suave
-- barra de corte abaixo da barra de tempo: arrastar as alças (ou setas) define o trecho; "música inteira" volta ao todo
-- salvo em \videos\Artista - Título.mp4 (se já existir: "... (2).mp4", nunca sobrescreve)

# AJUSTAR KARAOKE
- a barra id="corteTrilho" ficou ruim de determinar o ponto exato do corte, quando mexe no inicio ou fim mexe junto na linha do tempo e se perde referencia
- para ajudar, pode cruar dois botões abaixo de id="corteTrilho" ao lado de id="btnCorteInteira"
-- <i class="bi bi-align-start"></i>: ao clicar posiciona o inicio da barra id="corteTrilho" exatamente onde a linha de marcação do tempo estala
-- <i class="bi bi-align-end"></i>: ao clicar posiciona o final da barra id="corteTrilho" exatamente onde a linha de marcação do tempo estala
-- no video gerado, quando não há letra de música (intervalo) preencher com 3 x <i class="bi bi-music-note"></i> na mesma linha, indicando que é apenas música tocando e ninguém cantando

## Implementado (ajustar karaokê)
- arrastar as alças da barra de corte não move mais a linha do tempo (ela continua como referência)
- botões ao lado de "música inteira": bi-align-start / bi-align-end põem o início / fim do trecho
  exatamente na posição atual da linha do tempo (se cruzar a outra alça, a outra volta ao começo/final)
- vídeo: intervalos sem voz de 3 s ou mais (introdução, entre frases e final) mostram "♪ ♪ ♪" na rolagem,
  em branco no centro enquanto só a música toca

- no inicio do video mostrar o Titulo dele (grande) e embaixo o artista (pequeno) e em baixo o tom (no mesmo tamanho do artista) por 4 segundos com fade in e fade out
- se a intridução da música for menor do que 6 segundos (antes de começar a letra) criar um espaço antes sem som para complementar o tempo de 6 segundos

# AJUSTES
- eu já havia pedido que o botão Divir, além de fazer o que já faz, tbm na sequencia chama a função inicio
- na pratica, quando divido uma letra, eu já divido na posição da linha de tempo que ela vai ficar, por isso já pode chamar na sequencia 'Inicio'

- quero fazer uma modificação na navegação do teclado:
--  '←/→ 5 s': quero trocar para  '←/→ nota anterior/próxima'
-- ',/. nota anterior/próxima': ',/. 5 s'
-- ',/. nota anterior/próxima' + shift: ',/. 1 s' + shift
## Implementado (ajustes de edição e teclado)
- "✂ dividir" já faz o "⏱ início" da 2ª parte: ela começa no tempo atual da linha do tempo e a 1ª termina ali
-- se a linha do tempo estiver antes do início da frase, divide proporcionalmente ao texto (com aviso)
- teclado: ←/→ nota anterior/próxima · ,/. voltar/avançar 5 s · Shift + ,/. voltar/avançar 1 s

# GRAVAÇÃO
- reorganize o espaço em id="e2f538"
- adicione em id="e2f538" dois botão de gravação
-- <i class="bi bi-mic-fill"></i> inicia a gravação somente de audio
-- <i class="bi bi-camera-reels-fill"></i> inicia a gravação de audio e video
- em id="c41b8d", adicione mais uma opção, que levará a uma nova tela para configurar a gravação
-- origem do áudio
--- lista das opções de entrada de áudio
-- qualidade
-- outras funções relevantes de configuração da entrada de audio
-- origem do video
--- lista das opções
-- qualidade
-- outras opções
-- tela para visualizar o video
-- opção de gravar uma amostra de áudio e escutar que depois será descartada automaticamente
- ao gravar, as midias devem ser armazenadas em uma pasta \midias\[ID]\audio ou \midias\[ID]\video
- se ouver midia de audio ou video já gravada deve haver mais uma sessão em id="f6c55c"
-- essa sessão permite escutar a gravação sobre a faixa da música enquanto executado
-- deve obedecer a linha de tempo, devem estar sincromizadas
-- se for um video, deve mostrar uma pequena janela 25% da tela para visualização
## Implementado (gravação)
- e2f538: "velocidade" foi para baixo do tempo; novo bloco "Gravar junto" com bi-mic-fill (só áudio) e
  bi-camera-reels-fill (áudio + vídeo); clicar de novo, pausar, mover a linha do tempo ou mudar a velocidade
  encerra e salva (mover a música faria a gravação perder a sincronia)
- gravar começa a tocar a música se ela estiver parada; durante o vídeo a câmera aparece na janela flutuante
- nova aba "Gravação" (c41b8d): origem do áudio, nível de entrada, qualidade, canais, cancelamento de eco /
  supressão de ruído / ganho automático; origem do vídeo, resolução, quadros/s, qualidade, formato, espelhar,
  visualização da câmera; amostra de até 10 s que toca em seguida e é descartada (não é salva)
- arquivos em midias\[ID]\audio e midias\[ID]\video (gravacoes.py), com um .json ao lado guardando o ponto da
  música em que a gravação começa; o FFmpeg reempacota o arquivo para o navegador conseguir avançar nele
- f6c55c: seção "Minhas gravações" (só aparece se houver alguma): marcar toca junto, sincronizada com a linha do
  tempo; ◂/▸ acertam a sincronia (0,05 s; Shift 0,01 s); 🗑 apaga; volume próprio
- vídeo marcado aparece numa janela flutuante de 25% da largura da tela (um vídeo por vez)# 


# MIXAGEM
- em id="c41b8d" criar a opção MIXAGEM
- nessa nova tela deve ter a linha de tempo
- mostrar todas as faixas da música
- mostrar as gravações feitas de audio e video
- mostrar a tela do video
- para cada faixa deve ter a opção de:
-- volume
-- ganho
-- reverb
-- corus
-- pan
-- supressão de ruído
-- avanças ou retroceder 0.01s, 0.1s, 1s, 5s
-- deletar faixa ou gravação
- mostrar cores diferentes para:
-- faixa retirada da musica original através do modelo de ia
-- faixa de áudio gravada
-- faixa de video gravada
## Implementado (mixagem)
- nova aba "Mixagem" (c41b8d): transporte (⏮ −5 s ▶ +5 s, tempo, zoom, música inteira), régua e uma pista por
  faixa separada e por gravação, com forma de onda (mixagem.py, via FFmpeg) e o cursor da linha do tempo;
  clicar/arrastar navega, roda do mouse faz zoom
- cores: roxo = faixa separada pela IA, verde = áudio gravado, laranja = vídeo gravado (legenda no topo)
- tela do vídeo ligado dentro da aba (a janela flutuante "encaixa" ali e volta a flutuar nas outras abas)
- cada pista: tocar (mesma escolha do Player), volume, ganho (−12 a +24 dB), reverb, chorus, pan, supressão de
  ruído (filtro de graves + portão de ruído), deslocar −5/−1/−0,1/−0,01/+0,01/+0,1/+1/+5 s e 🗑 apagar
  (faixa: apaga faixas\[ID]\<faixa>.wav e tira de dados\[ID].json; reprocessar a música a separa de novo)
- os ajustes valem também no Player e ficam salvos nas preferências da música; duplo clique volta ao padrão

# MIXAGEM
- id="c5a1e9" está centralizado na tela
- mas essa tela precisa ser larga, ocupar todo o monitor na qual será colocada
## Implementado (mixagem larga)
- com a aba Mixagem aberta, a página perde o limite de 1400 px e ocupa toda a largura do monitor
  (as outras abas continuam centralizadas)
  
# MIXAGEM
- class="pista" está com height muito grande
- deve permitir ajuste com shift + scroll do mouse em cima de qqr uma delas
## Implementado (altura das pistas)
- controles mais compactos: os 6 efeitos numa linha só (coluna de controles com 560 px), pista bem mais baixa
- Shift + roda do mouse sobre qualquer pista muda a altura de todas (36 a 400 px, guardada no navegador);
  se a pista ficar mais baixa que os controles, eles ganham rolagem própria
  
# EDIÇÃO DE NOTAS MUSICAIS
- em id="linha" quero poder editar as notas musicais selecionadas em id="fonteNotas"
- a nota j´aparece em id="notaAtual"
- quero poder:
-- deletar a nova
-- alterar ela em id="notaAtual", ao lado pequenos botões up e dow, quando clicar neles altera a nota e soa um string mid da nova nota
-- autosave
## Implementado (edição de notas)
- a nota editável é a mostrada em "Nota" (notaAtual): a que está sob o cursor ou, com a música parada, a
  clicada em id="linha" (fica com contorno e o cursor vai ao início dela); Esc desmarca
- ao lado de notaAtual: ▲/▼ sobem/descem meio tom (Shift: oitava) e tocam a nova nota como corda dedilhada
  (Karplus-Strong, independe do mudo); 🗑 apaga a nota; teclado: ↑/↓ e Delete
- vale para a fonte escolhida em fonteNotas; salva sozinho (0,7 s depois) em dados\[ID].json
  (PUT /api/musicas/<id>/notas/<fonte>); reprocessar a música no solo.py refaz as notas e perde as edições

- abaixo de id="a8d3e6" quero um botão (icone) que vai unir a nota com a nota anterior, ou seja, deleta a nota atual e extende a nota anterior até cobrir a duração da nota deletada
- gostei do midi que você criou quando altera a nota, pode usar a mesma quando toca as notas sintetizadas habilitadas em id="d8e052"?
## Implementado (unir notas e som de corda)
- abaixo do 🗑 (a8d3e6): bi-arrow-bar-left une a nota com a anterior (apaga a atual e estende a anterior até o
  fim dela); desabilitado na primeira nota; salva sozinho como as demais edições
- o timbre "Guitarra (dedilhado)" das notas sintetizadas agora é a mesma corda da edição (Karplus-Strong, gerada
  uma vez por nota e reaproveitada); vale para todas as músicas que já usavam esse timbre
- correção: músicas com outro timbre salvo (órgão, senoidal, flauta) continuavam diferentes, e mesmo no dedilhado
  as notas curtas eram abafadas no fim da nota (soavam como estalo); agora as notas sintetizadas SEMPRE tocam a
  corda da edição, soando livre por até 1,6 s como ela (a nota seguinte abafa a anterior; acordes soam juntos);
  o seletor "Timbre" foi removido

- autosave não está funcionando como pedi. deleto a nota mas a mensagem aparece 'Notas não salvas: não encontrado
## Implementado (servidor desatualizado)
- causa: o app.py aberto era anterior à rota de salvar notas (o interface.html é lido a cada F5, o Python só ao
  iniciar o servidor); reiniciando o servidor o autosave funciona
- novo GET /api/servidor: diz se algum .py mudou depois que o servidor foi aberto; a interface verifica ao
  carregar e quando um salvamento de notas falha, e avisa para fechar o servidor e abrir o SOLO.bat de novo

- ao clicar em id="a8d3e6", já vai para a próxima nota
## Implementado (apagar e ir para a próxima)
- 🗑 (e a tecla Delete) apaga a nota e já seleciona a seguinte, com o cursor no início dela; na última nota
  apenas apaga
  
- em id="notaAtual", quando a nota fizer parte do campo harmonico definido em id="acordeAtual" ela fica verde, se não, vermelha
## Implementado (campo harmônico)
- campo harmônico do acorde = escala dele: maior → escala maior da raiz; menor (m) → menor natural; 7 → mixolídia
- notaAtual verde se a nota está nessa escala, vermelha se não; sem acorde no momento fica na cor normal;
  passar o mouse mostra o acorde e as notas da escala (já transpostos)
  
  - corrigindo
  - em id="notaAtual", quando a nota fizer parte do campo harmonico definido em id="tomAtual" ela fica verde, se não, vermelha
  - se a nota fizer parte de id="acordeAtual" ela fica azul (mesma cor de id="acordeAtual")
## Implementado (campo harmônico do tom + nota do acorde)
- azul (cor de acordeAtual): a nota é uma das notas do acorde atual (maior 1-3-5, m 1-b3-5, 7 1-3-5-b7);
  senão verde se está no campo harmônico do tom (escala maior, ou menor natural, da tônica); senão vermelha
- substitui a regra anterior (escala do acorde); passar o mouse explica a cor
- prioridade corrigida: o verde do tom vem antes; azul só para nota do acorde que está fora do tom
  (ex.: acorde emprestado), vermelho para o resto
-mas deve priorizar o verde do tom ao azul do acorde

- ctrl + z volta a ultima alteração
## Implementado (desfazer)
- Ctrl+Z na aba Player desfaz a última edição de notas (subir/descer, apagar, unir), uma por vez, até 200;
  a nota que voltou fica selecionada e o desfazer também é salvo sozinho
- vale para a música aberta (trocar de música limpa o histórico), mesmo que a fonte de notas tenha mudado;
  dentro de campos de texto (ex.: letra) o Ctrl+Z continua sendo o do navegador
  
# PUBLICAR NO YOUTUBE
- quero usar google-api-python-client videos.insert para publicar os videos da pasta \videos no youtube
- credenciais da api do youtube em \docs\client_secret_469674429318-g5ls5luslb3u6619c5n6a7dvqcnokof0.apps.googleusercontent.com.json
- em Biblioteca quero uma nova coluna em id="aa1bc3" 'YT' com um botão
-- esse botão deve aparecer somente se há um video da musica gerado na pasta \videos
-- pressionando o botão, chama a api e publica o video no youtube
-- não conheço a api, não sei quais informações devemos inserir lá, pode criar uma tela de parametrização da api
## Implementado (publicar no YouTube)
- youtube.py: videos.insert (google-api-python-client) com envio em partes e progresso; credenciais lidas
  de docs\client_secret_*.json, token da conta em docs\youtube_token.json, parâmetros e vídeos publicados
  em docs\youtube.json
- Biblioteca: coluna "YT" (depois de ⭐); o botão só aparece se há vídeo da música em \videos (procura
  "<Artista> - <Título>.mp4" e "(2)", "(3)"..., usa o mais novo); abre uma janela já preenchida
  (título, descrição, tags, visibilidade) para conferir e Publicar; o envio entra na mesma fila do
  processamento e mostra a %; publicado, vira um link para o vídeo
- botão "⚙ YouTube" (barra de filtros): conectar/desconectar a conta (login do Google numa janela) e
  parametrização: modelos de título/descrição/tags com {titulo} {artista} {tom} {categoria} {tags},
  categoria, visibilidade (padrão Privado), idioma, notificar inscritos, conteúdo infantil; tem o passo
  a passo do Google Cloud (ativar a YouTube Data API v3, cadastrar o redirecionamento
  http://localhost:8765/api/youtube/retorno no cliente OAuth, usuário de teste)
- reiniciar o servidor (SOLO.bat) e instalar: pip install google-api-python-client google-auth-oauthlib

-

# ALTERAR DESCRIÇÃO DO VIDEO
- na descrição do video que vai para o youtube quero adicionar a letra da música
- linhas separadas do modo como foi definida em id="letra"
## Implementado (letra na descrição)
- novo campo {letra} nos modelos do "⚙ YouTube": a letra salva em letras\ (a mesma do vídeo), uma frase
  por linha, igual ao painel da letra; entra no fim do modelo de descrição ("Letra:" + frases), inclusive
  na configuração que já estava salva em docs\youtube.json
- sem letra salva, o "Letra:" some da descrição; dá para conferir/ajustar o texto na janela Publicar,
  que avisa se a descrição passar dos 5000 caracteres aceitos pelo YouTube
  
# AJUSTES
- quando pressiono id="c4f9d1" para unir notas, a nota unida fica selecionada
- se eu clicar de novo em id="c4f9d1" sem querer ele vai unir com a nota anterior erroneamente
- para perder a seleção preciso dar play d enovo e parar
- quero que ao pressionar id="c4f9d1" ou id="d3f7b1" e unir, a nova nota perca a seleção, eu mesmo irei selecionar outra para unir ou alterar


## Implementado (ajustes)
- depois de unir (botão ⇤ ou c4f9d1), a nota resultante perde a seleção: "Nota" mostra "—", os botões
  de edição ficam desabilitados e um 2º clique não une mais com a nota anterior sem querer
- mesmo com o cursor parado sobre ela, a nota unida só volta a ser editável quando você clicar numa nota
  na linha do tempo, mover o cursor (←/→, barra, clique) ou der play
- subir/descer (d3f7b1) continuam mantendo a nota selecionada, para poder clicar várias vezes seguidas

# SOM DAS Notas
- O som das notas tocadas em id="d8e052"
- volte o select que selecionava o timbre
- mantenha esse timbre consruido em midi como opção (o atual)
- quero adicionar mais um:
-- Sem som metálico: Não use osciladores puros ou Web Audio API pura no JavaScript. Use a biblioteca Tone.js com Sampler carregando amostras reais (arquivos .mp3 ou .wav) de violino.
-- Som Suave (Aeroespacial/Pad): Configure o envelope do Tone.Sampler com um attack longo (cerca de 1.8 segundos) para o som entrar respirando, e um release longo (cerca de 2.5 segundos) para o som continuar ecoando suavemente após o comando de parar.
-- 3. Abordagem de Comunicação: O backend em Python deve apenas controlar os comandos ou dados (quais notas tocar), enviando um JSON ou via WebSocket para o frontend. Toda a geração do áudio deve acontecer no frontend (JavaScript) usando a placa de som local para evitar latência (atraso) no culto.
--
## Implementado (timbre das notas)
- voltou o seletor "Timbre" abaixo do volume das notas sintetizadas (salvo por música, como antes; timbres
  antigos como órgão/flauta viram a corda):
-- "Corda dedilhada": o som atual (Karplus-Strong gerado no navegador, o mesmo da edição de notas)
-- "Violino suave": Tone.js Sampler com amostras reais de violino (mp3), attack 1,8 s (entra respirando)
   e release 2,5 s (continua ecoando depois da nota e ao parar); volume e mudo valem igual
- arquivos locais em instrumentos\ (Tone.js 14.8.49 e instrumentos\violino\*.mp3, amostras do projeto
  tonejs-instruments, licença CC-BY 3.0), servidos pelo app.py em /instrumentos/: funciona sem internet
- o Python só entrega os dados das notas e os arquivos; todo o áudio é gerado no navegador, na placa de
  som local, no mesmo AudioContext das faixas (sem atraso entre eles). Tone.js e amostras só carregam
  quando o violino é escolhido; enquanto carregam, toca a corda
- a edição de notas (▲/▼) continua tocando a corda dedilhada
- reiniciar o servidor (SOLO.bat) por causa da rota nova /instrumentos/

- adicione no select (usando a biblioteca) Tone.js:
-- Acoustic Piano
-- Full Strings / Orchestra Pad
-- Shimmer Pad
-- Warm Pad / Ambient Pad
## Implementado (mais timbres com Tone.js)
- no select "Timbre", além da corda e do violino:
-- Acoustic Piano: Sampler com amostras reais do Salamander Grand Piano (instrumentos\piano, A1 a C8 em
   terças menores), release de 1,2 s
-- Full Strings / Orchestra Pad: Sampler com cello real no grave (instrumentos\cello) e violino do A3 para
   cima, cada nota dobrada uma oitava abaixo, attack 0,6 s / release 2,2 s, chorus e reverb de sala
-- Shimmer Pad: PolySynth (triângulo "fat", 3 vozes desafinadas) com a oitava de cima mais baixa,
   chorus lento e reverb longo (9 s), attack 1,4 s / release 3,5 s
-- Warm Pad / Ambient Pad: PolySynth (dente de serra "fat") por um passa-baixas em 950 Hz, chorus e
   reverb, attack 1,2 s / release 3 s
- cada timbre só carrega quando escolhido (até lá toca a corda); a dica abaixo do select descreve o
  timbre atual; trocar de timbre solta as notas do anterior; tudo continua local (sem internet)

# CORES
- na marcação das notas que aparece em id="linha"
- quero que as cores obedeça a mesma lógica de cores de id="notaAtual"
-- em relação a nota que está fora do tom ou então que pertence ao acorde## Implementado (cores das notas na linha do tempo)
- os blocos das notas em id="linha" usam a mesma lógica (e as mesmas cores) de notaAtual: verde no campo
  harmônico do tom; senão roxo/azul (cor do acorde) se é nota do acorde; senão vermelho
- o acorde usado é o que soa no início de cada nota (o mesmo de "Nota" com o cursor no início dela)
- a nota que está soando fica opaca e com borda clara; as demais um pouco transparentes
- sem tom detectado e fora do acorde, a nota fica com as cores de antes (cor da faixa de origem / laranja)
- Cello (Violoncelo): Sampler com amostras reais de violoncelo (instrumentos\cello, C2 a C5), attack
  0,15 s / release 1,5 s e reverb leve; acima do C5 as amostras são esticadas
  
# Piano
- na parte de baixo de id="de872a" quero
- inserir a imagem renderizada de 6 oitavas de um piano
- quando a nota for tocada em id="linha", marcar a tecla do piano será marcada (usando o mesmo esquema de cores das notas)
- as notas do acorde também deve ser marcado, simulando a mão esquerda, usando o mesmo esquema de cores das notas
- importante o teclado ter as proporções reais
- como são 6 oitavas, pode sobrar espaço antes ou depois, deve centralizar horizontalmente em id="de872a" 
- faça uma primeira versão
## Implementado (piano, 1ª versão)
- abaixo da linha do tempo (dentro de de872a): teclado de 6 oitavas, C1 a C7 (73 teclas), desenhado em
  canvas com as medidas reais (branca 23,5 × 150 mm, preta 13,7 × 95 mm, pretas na posição real);
  ocupa a largura disponível mantendo a proporção, até 140 px de altura; sobrando espaço, fica centralizado
- melodia: a tecla da nota de "Nota" (a que está tocando, ou a selecionada) fica colorida com a cor de
  notaAtual e uma bolinha branca
- mão esquerda: baixo (fundamental na oitava 2) + tríade/tétrade do acorde atual a partir da fundamental
  na oitava 3, mesmas cores (verde no tom, cor do acorde fora dele), um pouco mais claras que a melodia
- acompanha a transposição; notas fora de C1–C7 não aparecem

- o piano ficou bom
- mas a nota da mão esquerda (acorde)
-- quero que tenha a mesma cor da fonte de id="acordeAtual" (indicando que é acorde)
-- percebi que as notas ficaram longe, o que seria impossível tocar com a mão
-- as notas do acorde precisam estar próximas no teclado
-- as notas do acorde precisam estar mais a esquerda, para não disputar a mesma região do teclado da mão direita

## Implementado (mão esquerda)
- as teclas do acorde ficam sempre na cor de acordeAtual (a cor de "Acorde"), opacas; a melodia segue
  com as cores de notaAtual e a bolinha branca
- acorde em posição fechada (tríade, ou tétrade no 7, abrindo no máximo uma 7ª: cabe na mão), sem o
  baixo separado, com a fundamental entre C2 e B2: bem à esquerda, longe da região da mão direita


# CRIAÇÃO DO VIDEO
- quando criar o video em id="btnCriarVideo"
- quero inserir o piano id="piano" na base do video, nas mesmas cores das marcações das notas
- ao lado esquerdo do piano, insira o acorde id="acordeAtual" (na mesma cor  de id="acordeAtual")
- ao lado direito do piano insira a nota tocada naquele momento id="notaAtual" (na mesma cor de id="notaAtual")
- como vamos inserir o piano embaixo precisamos subir um pouquinho o ponto onde a letra é marcada de amarelo, ou seja, o centro do video que é referencia onde deve ser cantado
## Implementado (piano no vídeo)
- video.py: faixa de 150 px na base do vídeo com o mesmo piano do player (C1–C7, medidas reais), a nota
  da melodia nas cores de notaAtual (com a bolinha branca) e o acorde na mão esquerda na cor de acordeAtual;
  cores do tema escuro da interface
- à esquerda do piano o acorde (cor de acordeAtual), à direita a nota tocada (cor de notaAtual); "—" em
  cinza quando não há
- a letra ficou na área acima do piano: a frase atual (onde marca o amarelo) subiu de 360 para 285 px,
  com o esmaecimento acima do piano
- as notas são as da fonte escolhida em "Notas exibidas e tocadas" (a interface manda --notas), já com
  as edições salvas; se ainda há edição de nota para salvar, o vídeo pede para aguardar; no tom original
  (o áudio do vídeo não é transposto)
- reiniciar o servidor (SOLO.bat) para o app.py repassar a fonte das notas (sem isso usa "solo")

# AJUSTE VIDEO
- o som do timbre escolhido em id="timbre" não foi renderizado no video
- precisa renderizar o tmbre escolhido
- se id="btnMudo" estiver mute, não deve renderizar
- no video, logo acima do piano, no lado edquerdo da tela uma pequena marca dágua com: class="bi bi-youtube" + @Louvores.Karaoke## Implementado (som das notas e marca d'água no vídeo)
- ao criar o vídeo, se as notas sintetizadas não estão no mudo (btnMudo) e o volume é > 0, o navegador
  renderiza o som das notas do trecho com o timbre escolhido em id="timbre" (corda: OfflineAudioContext;
  Tone.js: Tone.Offline com o mesmo instrumento), no tom original, com o volume proporcional ao das
  faixas no player (volume das notas ÷ volume das faixas, até 2×); envia o WAV (PUT
  /api/musicas/<id>/video/notas, guardado na pasta temporária do sistema) e o video.py mistura com as
  faixas (--sintetizado) e apaga o arquivo no fim; no mudo, o vídeo sai só com as faixas
- marca d'água no canto esquerdo, logo acima do piano: logo do YouTube (desenhado, como o bi-youtube)
  + "@Louvores.Karaoke", branca com 60% de opacidade
- reiniciar o servidor (SOLO.bat) por causa da rota nova

# ATALHO DE BOTÕES
- quero criar um atalho de teclado
- quando estiver com foco em id="linha"
- considerar maiusculas e minusticas no teclado
-- q: id="btnNotaCima"
-- w: id="btnNotaBaixo"
-- a: id="btnNotaExcluir"
-- s: id="btnNotaUnir"

- crie uma novo botão com um icone correspondente
- esse botão deve criar uma nota nova na posição da linha de tempo
- essa nota deve ser igual a anterior e deve ter 0.25s
- esse novo botão será chamado por 'd'

- acho que essa instrução causou um problema (- quando estiver com foco em id="linha")
- o atalho só funciona se eu clicar com o mouse na nota
- o atalho do teclado é justamente para não usar o mouse e tudo ficar mais rápido
- vamos fazer diferente, o atalho só não funciona quando eu estiver escrevendo um texto editando a letra da música, para não dar confusão
- outra mudança:
-- id="btnVoltar1" deve voltar 0.1s
-- id="btnAvancar1" deve avança 0.1s
-- ambos mantem atalho de tacldo já existente

-- id="btnVoltar1" deve voltar 0.1s - ATALHO ","
-- id="btnAvancar1" deve avança 0.1s - ATALHO "."

-- no forms em id="btnConfigYoutube" insira um campo apenas para as palavras chave
-- algumas palavras chave sempre padrão será:
--- #{titulo} (tudo junto sem espaço)
--- #{artista} (tudo junto sem espaço)
--- #karaoke
--- #playback
--- #letra
--- #piano
--- #cifra
--- #louvor
--- #gospel
--- #worship
--- #pianotutorial
--- #tutorialpiano
--- #jesus
-- o campo deve permitir edição para adiccionar e remover palavras chaves
-- inserir as palavras chaves na posição exata da api para alimentar o youtube

# FAIXA VOCAL
- quando clicar em id="btnVozGrave" a linha de tempo se posiciona no inicio dessa nota (na primera vez que ela aparece)
- quando clicar em id="btnVozAguda" a linha de tempo se posiciona no inicio dessa nota (na primera vez que ela aparece)

# ENCAIXE DA LETRA
- no modo ediaçõ (id="btnEditarLetra") quero adicionar duas funcionalidades
- um botão que deleta toda a letra deixando apenas um id="letra-0-texto" em branco
- vou adicionar a letra inteira nesse id="letra-0-texto"
- quero um segundo botão (icone correspondente) que irá encaixar a letra na música
-- essa sugestão você deu no inicio do projeto e eu não aceitei, mas agora entendi a necessidade
-- irá encaixar a letra na música
-- mesmo que haja repetição e a letra não possua a repetição ela vai duplicar a letra e encaixar no lugar certo

- deu um erro de encaixe a partir dos 02:53:32 da música 'Lugar Secreto'
- inseriu varias frases em um intervalo muito pequeno
- acredito que precise de outro método para ser mais assertivo 

# INSERIR VIOLÃO
- em id="piano"
- remova uma oitava apenas
- no local dessa oitava insira o braço de um violão para mostrar a cifra do acorde
- normalmente mostram 5 casas e na vertical em sites de cifras
- obedeça as proporções para ser natural
- use uma biblioteca como SVGuitar ou melhor
- a cifra deve ficar ao lado esquerdo do piano
- deve mostrar o acorde que está em id="acordeAtual"

- o video gerado na pasta \videos quando clicar em id="btnCriarVideo" também precisa ter o mesmo conteudo de id="instrumentos"
- deve observar o alinhamento que corrigimos há pouco, também corresponder ao video
- no video o restante permanece igual
-- acorde representado a esquerda e nota a direita (isso não muda)
- a cifra de violão toma o espaço de uma aoitava removida do teclado (assim como em id="instrumentos")

- a marca dagua do video, quero um pouco menor 75% do tamanho atual e abaixo dos instrumentos, aainda a esquerda

- ao clicar e id="btnCriarVideo", depois de criar o video como já faz hoje deve:
-- criar um novo video para o instagram e salvar em \videos\instagram
-- esse novo video deve ter:
--- Resolução de 1920 x 1080 pixels, com proporção 16:9.
--- MP4 (com codec de vídeo H.264 e áudio AAC).
--- 30 fps (quadros por segundo).
--- também deve ter os instrumentos na parte de baixo
--- sem a marca dagua
--- a indicação do acorde (id="acordeAtual") diferente do video padrão fica em cima do lado esquerdo
--- a indicação da nota  (id="notaAtual") diferente do video padrão fica em cima do lado direito

# BUG
- você gerou um video na pasta \videos\instagram exatamente igual ao que já é feito hoje, ignorando toda a instrução que passei acima nas linhas 856 a 864


- ao lado de id="ytDesconectar"
- crie um link para  https://studio.youtube.com/channel/UCasDeC98FcleYN-dWcpoqsQ/analytics/tab-overview/period-default

# BOTOES GERAR VIDEO
- mova id="btnCriarVideo" para uma coluna em id="tabelaMusicas" apenas com um icone
- ao lado crie outro botão apenas para o video que será salvo em \videos\instagram
- vamos separar, quero gerar eles independente

# MULTISELECT
- id="fonteNotas" deve ser multiselect
- o que for selecionado em id="fonteNotas" deve aparecer em id="linha"
- separar em cores por legenda

- você criou um option que eu não pedi
- quero checkbox e se eu selecionar dois quero tocar e editar os dois juntos, mas identificar com cores diferenets em linha

- o volume das notas sintetizadas está muito baixo
- quero ter maior controle, está no 100% e ainda está baixo
- esse mesmo volume deve corresponder ao volume dos videos gerados (mixagem)
- quero adicionar flauta e saxofone em id="timbre"

# SUSTAIN
- abaixo de id="volumeSint"
- pode ter outro slice que começa em 0 para controlar o sustain e attack das notas? tocadas da seleção de id="timbre"

- em id="col-youtube" o logo do youtibe indica que já fiz o upload,
- mas se eu quiser atualizar o video, é possível?
- ou fazer outro upload e deletar o video antigo manualmente? Se sim, não aparece o botão uma vez que já fiz o upload, ele precisaria aparecer de novo

- na legenda em class="legenda" ficou ruim poque já tinhamos definido que notas fora da escala ficam vermelha e deve obedecer a coloração de em id="linha"
- e voz ficou sempre vemelho, o que prejudica a visualização das notas fora
- na legenda não pode ter nenhuma vermelha, e manter vermelho para as notas fora do tom seguindo a mesma cor de id="notaAtual"
- tem bug em id="btnVozGrave", pois na musica BOndade e Deus tem um C#3 e mostra como id="btnVozGrave" um D3
- não entendi ou não lembro o que significa a barra continua verde e vermelha em cima de id="linha"


- nos incluimos attack e sustain no controle das notas sintetizadas, mas não se refletiu esse efeito no video gerado
- o audio do video precisa refletir o mesmo que configuramos na interface, volume, efeitos atuais e os possiveis que vamos criar
- aproveitando, crie mais um slider com o efeito reverb e chorus

- na api de upload do youtube marque a opção para bloquear links indesejados
- na linha de tempo abaixo de id="linha" quero
-- poder clicar nela e fazer uma marcação. nesse ponto o tempo fiará em negrito e terá uma linha pontilhada vertical cinza em id="linha"
-- posso fazer mais de uma marcação
-- crie botão ao lado de id="btnVozAguda" com icone que remove as marcações

- em id="timbre" adicione:
-- Choir Aahs (Vozes abrindo em "Ah")
-- Voice Oohs (Vozes suaves em "Uh")
-- Synth Voice / Solo Vox
- sugesrtão WebAudioFont

- adicione mais um Ahhs usando:
-- file: 0530_Soul_Ahhs_sf2_file.js
-- variable: _tone_0530_Soul_Ahhs_sf2_file
-- MIDI: 53. Voice Oohs: Ensemble

- crie uma rota de documentação com link e insira esse link aqui: https://surikov.github.io/webaudiofontdata/
- pode remover id="a6c3e9"
# BUG
-- criei o video da musica Acalma o Meu Coração e não saiu a nota sintetizada, nesse caso escolhi Voice Oohs...


- em id="ytDescricao" quero adicionar a indicação da extensão vocal da música (id="btnVozGrave" e id="btnVozAguda")

# CONTROLE MIDI
- tenho um teclado yamaha dgx 230
- ele tem entrada usb e já usei ele para controlar o software bandlab (as vezes funciona e as vezes não)
- gostaria de usar ele para controlar o id="piano"
- considerando a sensibilidade das notas quando pressionada
- sustain
- e demais recursos de controle midi que ele apresenta
- gostaria que as notas ficassem gravadas em id="linha" no tempo certo em que forem tocadas 
- para isso preciso ter um modo REC MIDI
- essa gravação seria mais uma faixa mas de outra categoria em um seletor select separado, pois posso gravar mais de uma faixa midi (similar a id="btnGravarAudio")
- talvez eu precise ter mais um route de configuração do controlador midi


# CATEGORIA DA Voz
- ao lado de id="btnLimparMarcas"
- considerando a extensão vocal
- gostaria de classificar o tom como Masculino ou Feminino
- além disso:

• Soprano: É a voz mais aguda das mulheres. Tem grande facilidade para alcançar notas altas.
• Mezzo-soprano: É a voz intermediária ou média. Fica entre o soprano e o contralto, com bom equilíbrio entre graves e agudos.
• Contralto: É a voz mais grave entre as mulheres. Tem facilidade e maior riqueza sonora nas notas baixas.

• Tenor: É a voz mais aguda entre os homens. Alcança notas mais altas com maior facilidade.
• Barítono: É a voz intermediária ou média. É o tipo de voz masculina mais comum, com um timbre encorpado que transita bem entre graves e agudos.
• Baixo: É a voz mais grave entre os homens. Consegue produzir sons profundos e pesados.

# SOBRE O CONTROLE MIDI
- eu não sou o administrador desse computador
- vou precisar usar outro e passar esse codigo pelo git no repositorio contido em C:\Users\cs385499\PycharmProjects\TelaCifras
- para isso, quero passar sem os modelos, pois quando rodar no outo computador pela primeira vez deverá baixar os modelos
- e deve enviar sem os arquivos de música e videos (que são pesados)
- já está dessa maneira?

# GRAVAÇÃO midi

- já existe um botão que incia a grabação de MIDI id="a1f6c3"
- para iniciar a gravação aguarda 3 segundos antes de começar (depois de apertar o botão)
- para parar a gravação pode apertar no mesmo botão ou em Pausar (id="btnPlay")
- se apertar em id="a1f6c3", automaticamente pausa a música
- na gravação do MIDI posso ajustar o Sustain. Pode ter um Checkbox que se flegado assume o Sustain dos controles já existentes

- não precisa existir id="seletorMidi"
- as gravações de midi podem estar em id="faixa"
- mas agora id="faixa" deve:
-- indicar de cor diferente que é um MIDI gravado
-- permitir editar o nome de todas as faixas
-- permitir deletar todas as faixas
-- quero transformar id="faixa" e id="fonteNotas" em uma só tabela com as mesmas funcionalidades
-- ou seja, posso selecioar as faixas que são todas e as notas que aparecem (incluindo as midis gravadas)
-- para as midis gravas posso escolher outros timbres (ou seja, um id="timbre" para cada faixa de MIDI gravada)
- as faixas midi gravads devem aparecer em id="aba-mixagem" e lá também posso mudar o timbre

# INTERFACE
- id="tabelaMusicas" deve permitir deletar
- estou tentando processar a única musica dentro da pasta audio e está dando erro

- id="aba-biblioteca" deve ter opção de marcar e desmarcar todas as linhas (e selecionar algumas com checkbox)
- ter uma opção excluir selecionadas
-- a exclusão deve limpar os dados no banco de dados e os arquivos correlacionados
- deve ter uma opçã de processar todas os audios que ainda não foram processados
-- se der erro, deve tentar de novo

# QUERO ORGANIZAR A LINHA EM TABS
- na primeira tab é exatamente como está, formada por 
-- id="linha"
-- id="instrumentos"
- a segunda tab é a renderização de como ficará o video do youtube, para permitir visualizar
- a tarceira tab é o video do instagram, também para visualizar. por ele ser vertical pode ficar menor ocupando o centro da tab, é apenas para visualização
- os videos devem ser renderizados em html mesmo e não no formato de video (para ser mais rápido) e poder editar se algo der errado
- hoje preciso gerar os videos para identificar erros e depois editar
- quando clicar em um dos botões de id="bib-08736966-video" os videos serão renderizados como estão no html, cada um no seu formato específico
- id="barra" e id="corte" ficam de fora das tabs, na posição onde estão para controlar a visualização

# INTERFACE
- a coluna id="faixa-col-audio" precisa ter um checkbox em cima para marcar/desmarcar todos
- ao lado de id="f4c8a1" quero um botão com icone apenas (correspondetente) que faça o autotune de todas as notas mostradas naquele momento na linha
-- deve percorrer nota a nota, e a que estiver fora do tom deve ter o ajuste automático para a nota mais próxima dentro do tom


# POSSIBILIDADE
- não implemente nada, quero explorar uma possibilidade
- normalmente as faixas isoladas das notas apresentam alguns erros, principalmente no solo e na voz
-- notas fora do tom
-- notas que não existem
-- notas durando mais tempo do que deveriam
-- notas "quebradas", ou seja, notas que possuem sustentaçã mas que por algum motivo aparecem repeditas várias vezes em sequencia
- nessa aplicação identificar a nota corretamente é um requisito obrigartorio
- é possível criar uma "varinha mágica" para reprocessar somente uma faixa de notas?
-- seleciono apenas a faixa da voz em id="faixa-col-audio-rotulo"
-- só funciona se eu selecionar apenas uma faixa
-- aperto a varinha mágica
-- reprocessa a voz com o objetivio de acertar as notas
- isso pode traze algum ganho ou é ireelevante a chance de processar igual já fez no primeiro processamento é alta?
- não implemente, escreva abaixo sua conclusao

## CONCLUSÃO (análise da "varinha mágica" para reprocessar uma faixa)

**Reprocessar do mesmo jeito é irrelevante.** Hoje as notas saem do basic-pitch (modelo ONNX, `solo.py` →
`transcrever`) com parâmetros fixos (`onset_threshold=0.5`, `frame_threshold=0.3`, mínimo de 0,06 s) e depois
passam por `extrair_melodia`. Tudo isso é determinístico: o mesmo `vocals.wav` com os mesmos parâmetros dá
exatamente as mesmas notas. A chance de "processar igual" não é alta, é de 100%. A varinha só traz ganho se usar
**outro método** (ou outros parâmetros) na segunda passada.

**Por que os erros aparecem (e por que dá para melhorar):**
- O basic-pitch é um transcritor **polifônico** genérico, pensado para instrumentos. A voz é **monofônica**
  (uma nota por vez), com vibrato, glissando e consoantes. O modelo divide o vibrato e as variações de
  intensidade em várias notas ("notas quebradas"), confunde harmônicos com notas ("notas que não existem")
  e estende a nota no reverb que sobra da separação do Demucs ("notas durando mais").
- `extrair_melodia` só escolhe a nota mais aguda entre as fortes. Ela não junta notas repetidas nem
  conhece o tom.

**O que uma varinha com ganho real faria (só na faixa selecionada, especialmente na voz):**
1. **Detector de altura monofônico** em vez do basic-pitch: o `librosa.pyin` já está instalado e não precisa
   de dependência nova. Opções melhores para canto: `torchcrepe` (o torch já vem com o Demucs) ou RMVPE
   (o estado da arte para voz, com modelo baixado na 1ª vez). Eles dão uma curva de altura contínua com a
   confiança de "há voz aqui", e isso resolve a maior parte das "notas que não existem".
2. **Segmentação em notas a partir da curva:** suavizar com filtro de mediana (tira o vibrato), arredondar
   para o semitom com **histerese** (só muda de nota se ficar fora por mais de ~80 ms) e **juntar notas
   iguais e seguidas** com intervalo pequeno. Isso resolve as "notas quebradas".
3. **Fim da nota pela energia/confiança** (quando a voz para), não pelo modelo. Isso resolve as "notas
   longas demais".
4. **Usar o tom já detectado** como preferência: na dúvida entre duas notas vizinhas, fica a que está no tom
   (o mesmo critério do botão de autotune, mas aplicado à curva real, antes de virar nota).
5. **Usar a letra encaixada** (`letraPalavras`, que vem do wav2vec2 no `encaixe.py`) como pista de início
   de nota: cada sílaba cantada costuma ser uma nota nova. Isso ajuda a separar notas repetidas
   legítimas de notas quebradas.

**Como seria na interface:** quando apenas uma faixa estiver marcada na coluna "Notas" (o rótulo
`faixa-col-audio-rotulo` é o cabeçalho de "Áudio"; o natural é usar a seleção de "Notas"), a varinha manda
essa fonte para uma rota nova do servidor (ex.: `POST /api/musicas/<id>/reprocessar/vocals`). O servidor
roda os passos acima só sobre `faixas/<id>/vocals.wav` (sem refazer o Demucs: leva segundos, não
minutos) e devolve as notas novas. O ideal é poder **desfazer** (Ctrl+Z) ou comparar antes de aceitar, e
aplicar só no **trecho visível** da linha do tempo, para não apagar correções manuais já feitas no resto.

**Veredito:** vale a pena, principalmente para a **voz**. Para o **solo** (guitarra/teclado), o basic-pitch
já é adequado. Lá o ganho vem do pós-processamento (passos 2, 3 e 4), não de trocar o detector. Mesmo
assim não existe 100% de acerto automático: a separação do Demucs deixa vazamento de outros instrumentos. A
varinha reduz bastante a edição manual, mas não a elimina. Sugestão de ordem: primeiro pYIN + passos 2 a 4
(sem dependência nova); se ainda errar muito, testar torchcrepe/RMVPE.

- coloque esse notão ao lado de id="btnFaixasTodas"

- na musica Tua é a gloria, pelo minuto 2:39 (aproximadamente) há uma mudança de tom.
- os modelos não entenderam isso e depois disso muita nota ficou faltando
- aparentemente não entendeu
- eu não sei se ele busca notas no tom e quando não encnotra omite (parece que foi isso que aconteceu)

- falhas na identificação das notas em:
-- 2:48.65
-- 3:06.98
-- 3:43.53
- notei ue são as mesmas notas, em um refrão que rse repete e sempre nesse pequeno trecho tem erro

# ENCAIXAR LETRA
- a função chamada por id="f3b9d4" não está funcionando como deveriam
- quando especifiquei ela, descrevi que em trechos repetidos da música, a letra inicialmente inserida na caixa de texto não teria essas repetições e a função deveria encontrar as frases e ENCAIXAR
- por exemplo a música Tua é a Glória 7f954864 está com falhas justamente nas repetições
- além disso essa mesma música começou errado
- enfim, essa função possui muitas falhas e não está servindo ao seu propósito

- percebi que as notas sintetizadas estão com pequeno atraso, não consigo quantificar apenas ouvindo, mas algo em torno de micrsegundos
- para resolver isso de forma mais assertiva, gostaria de botões antes de id="btnInicio" que eu possa avançar ou recuar na linha de tempo 0.01s toda faixa das notas sintetizadas apenas das faixas selecionadas em id="faixa-col-notas"

- na musica 7dff3523 na faixa Guitarra / violão existe um dedilhado
- as notas sintetzadas só aparece um F#4 de forma constante (o que está errado)
- tentei reprocessar e não deu certo
- sem quebrar o que já fizemos para voz (que funcionou) é possível melhorar a identificação do dedilhado?

# VISUAL Piano
- em ambos os vídeos quero fazer um recurso de Piano Visualizer com falling notes (piano roll)
- mas quero que os feixes de notas sejam mais opacas para não atrapalhar a visualização da letra da música e apareçam atrás da letra (de forma suave)
- no final de cada nota quero um gradiente suave, mostrando o decaimento da nota

- as notas dos acordes não estão aparecendo no visualizer
- além disso quero um checkbox que habilite ou não a visualização do falling notes

- no inicio do video, onde é mostrado o nome, cantor e tom, abaixo do tom informe id="categoriaVoz"
- o mesmo em id="ytDescricao" abaixo de Extensão vocal: {extensao}
- e o mesmo em id="ytTitulo" no final

- já havíamos corrigido isso, id="btnVozGrave" e id="btnVozAguda" não estão trazendo os valores corretos
- a música 7dff3523 mostra id="btnVozGrave" mas tem um F#2 na linha
- deve considerar a música inteira de todas as id="faixa-col-notas" selecionadas
- havendo alteração nas notas deve refletir automaticamente 

- no teclado (tanto na interface quanto nos videos) gostaria de criar uma leve "sombra" nas notas fora da extensão vocal apenas das notas da faixa da voz
- ou seja, nessa faixa o teclado fica como está
- nos demais fica essa sombra
- a ideia é mostrar a xtensão vocal no teclado mas sem esconder as outras notas

- ficou bom, mas o cinza escuto não deixa visie a tecla do acorde que tbm é escura, precisa ter um contraste

# MUDAR O TOM
- quero avaliar uma forma de mudar o tom das músicas
- sei que é algo complexo porque estou misturando MIDI com faixas dos instrumentos com notas sintetizadas
- mas no resultado final, nunca uso a voz, logo:
-- notas sintetizadas é fácil
-- percussão não precisa
-- o foco é na harmonia base, pads, violão, baixo, piano....
-- é possível mudar o tom mantendo uma qualidade?
-- não implemente nada, apenas vamos avaliar a possibilidade
## CONCLUSÃO (mudar o tom)
- é possível; pelo que se sabe do Rubber Band, a qualidade é boa em até ±2/3 semitons; acima de ±4 começam artefatos (ataques "borrados", grave com leve fase)
- ferramenta: Rubber Band (já disponível no ffmpeg instalado, filtro `rubberband`); costuma soar melhor que o librosa (vocoder de fase simples)
- teste em 7dff3523 (30 s, +2 semitons, cada faixa separada e depois misturada; bateria sem transpor): amostras em scratchpad/tom
- custo: ~18 s por faixa de 5 min; 5 faixas ~1,5 min (paralelo menos); feito uma vez e guardado em cache (faixas/<id>/tom+N/)
- não dá para fazer em tempo real no navegador com essa qualidade: as faixas seriam pré-renderizadas no servidor ao escolher a transposição
- transpor cada faixa separada tende a soar melhor que transpor a mistura (falta confirmar ouvindo) (o vazamento da voz nas faixas também sobe, mas a voz não é usada)
- quanto menor o deslocamento, melhor: subir 5 soa melhor que descer 7 (mesmo tom, uma oitava de diferença); ±6 é o pior caso
- notas sintetizadas e MIDI: só somar a transposição (já é feito no player); bateria: não transpor
- o vídeo usaria as faixas transpostas na mistura (OfflineAudioContext) e o teclado/acordes no tom novo

- crie um select com as possibilidades de transposição: em semitons para cima e para baixo e ao lado de cada um a nova categoria de voz qe vai ficar o resultado
- coloque ao lado de id="categoriaVoz"
- e ao lado um botão para renderizar
- e ao lado um botão que retorna ao original
- não deve sobrescrever os arquivos originais, voltar para o original apaga as faixas transpostas de audio e volta a valer as originais, para hão haver perda de qualidade ou distorções pela mudança

- quando pressionar id="bib-7dff3523-video-padrao" ou id="bib-7dff3523-video-instagram" e os arquivos já existirem deve sobrescrever. atualmente está riando uma cópia

- a musica c5630915 em 00:50 aproximadamente entra um coro de voz e as notas não foram capturadas no reprocessamento, deixando uma parte da musica sem notas

# TECLADO INTERATIVO
- quero eu mesmo corrigir algumas notas em alguns trechos
- para isso quero que o teclado do computador posso soar notas
- quero um botão com icone apenas antes de id="btnNotasAtrasar" que habilite essa função
- ao habilitar quero que as teclas do teclado atuem somente no tom da música ou no tom do trecho da música
- por exemplo, se o tom for C:
-- Q: C2
-- W: D2
-- E: E2
-- R: F2
-- T: G2
-- Y: A2
-- U: B2
-- I: C3
-- O: D3
-- P: E3
-- A: F3
-- S: G3
-- D: A3
-- F: B3
-- G: C4
-- H: D4
-- J: E4
-- K: F4
-- L: G4
-- Ç: A4
-- Z: BAIXO UMA OITAVA
-- X: SUBO UMA OITAVA
-- C: BAIXO UMA NOTA
-- V: SUBO UMA NOTA
-- B: habilita/desabilita sustain
-- ESPAÇO: enquanto segura habilita sustain
- ao habilitar deve mostrar o atalho de teclas em id="piano" e ocultar o atalho quando desabilitado
- mas o atalho de teclas não deve ser mostrado nos videos gerados
- reconhece maiuscula e minuscula
- pode ser polifonico (permite "gravar" duas ou mais notas ao mesmo tempo na linha
- o teclado do computador não permite a sensibilidade, mas permite segurar a nota
- o som que deve soar é o mesmo escolhido em id="timbre"

- para gravar
- quando eu estiver pausado e selecionar id="btnGravarMidi" continua pausado
- mas se id="b7e3c9" também estiver selecionado deve:
-- iniciar a tocar e gravar a faixa midi no exato momento que eu apertar qqr tecla do teckado, ou seja, começa a gravar no momento que começa a tocar
-- a letra "N" pausa novamente a musica e para a gravação salvando a nova faixa MIDI
- não quero mais isso: B: habilita/desabilita sustain está atralahando. Espaço deve ser para e continua o play, como antes

- quero uma funcionalidade de copiar e colar as notas midi gravadas
- em pause, coloco o cursor na linha em uma posição
- seguro shift e com left/right e <, > do teclado eu vou selecionando as notas
- quando seleciono elas, copio com ctrl+c
- depois vou na posição da linha em que quero colar as notas
- pressino ctrl+v e elas são coladas

- eu já fiz ajuste de letra varias vezes, mas por que sempre mostra (Encaixando a letra pela voz… na 1ª vez de cada música o modelo analisa a faixa de voz (1 a 3 min; na 1ª vez de todas ainda baixa o modelo, ~1,2 GB).)
- baixa o modelo 1.2G todas as vezes?

# Thumbnail 
- quero fazer tumbnails dos videos assim
- deve ter o mesmo tamanho/dimensão da tela dos videos para o youtube
- devem ser salvos na pasta \videos\thumbnail com o mesmo nome do video mas com a extensão.jpg
- é uma umagem de capa, deve ter:
-- titulo da música
-- artista
-- tom (meu tom)
-- texto "TUTORIAL PIANO & VIOLÃO"
-- Texto à esquerda: tipografia clara, hierarquia simples e espaço negativo para facilitar a leitura.
-- Fundo: preto azulado ou grafite, com formas geométricas discretas e uma textura sutil.
-- Acabamento: linhas finas e textura muito discreta, sem reflexos exagerados, partículas luminosas ou efeitos 3D.
-- deve ter o piano e o violão na mesma posição do video com algumas notas aleatórias caindo do piano e no graço do violão o tom da música
-- a imagem deve ser gerada no final do video clicando em nas ids com "video-padrao" dessa forma sei as informações que devem ser criadas
- ao clicar para fazer upload no youtube deve mandar o Thumbnail

# DELETAR
- já tenho a funcionalidade de selecionar um trecho de notas em linha e copiar e colar
- quero poder pressionar delete no teclado e deletar somente o trecho selecionado das notas selecionadas- somente as notas que estão marcadas em id="faixa-col-notas"

# INTRODUZIR UMA MÚSICA
- hoje inicio o processo copiando e colando um arquivo de audio na pasta \audio
- depois disso ele já aparece em id="tabelaMusicas"
- tenho uma extensão em C:\dev\Linkedin que possui uma funcionalidade que identifica audio na página "escuta" e faz download dele
- quero inserir essa funcionalidade 
- posso ter um primeiro botão em id="c41b8d" que vai para uma tela que:
- insiro o link do youtube
- embeda o video, escuta ele, baixa o audio e salva em \audio
- a partir daí tudo continua como está
- mas em id="tabelaMusicas" fica a informação do link original do video do youtube para rastreamento se necessário
- não sei se a melhor abordagem é embedar o video e escutar ele, o que preciso é salvar o arquivo mp3 em \audio
- você pode sugerir outra melhor prática já existente que desconheço
# PADRÃO
- ao iniciar uma nova edição

# AUTOMAÇÃO
- ao pressionar em 'Abrir' (exemplo id="bib-7d6c27a1-abrir-abrir") pela primeira vez
-- somente na primeira vez, logo depois de 'PROCESSAR'
- vai para id="tab-player" exatamente como faz hoje
- em ÁUDIO (id="faixa-col-audio-rotulo") seleciona todos em 
- em NOTAS (id="faixa-col-notas") apenas a linha de id="faixa-vocals-rotulo"
- id="volumeFaixa" em 80
- id="volumeSint" em 85
- id="ataque" em 0,07
- id="sustain" em 1,8
- id="reverbNotas" em 10%
- id="chorusNotas" em 15%
- id="timbre" 'Acoustic Piano' id="timbre"
- chamar a função id="btnVarinha" 'Reprocessar notas'
- chamar essa rota somente na primeir vez que Abrir a música, logo depois de reprocessar
- nas proximas vezes
-- salva os parâmetros alterados no cache (como é atualmente)
-- não chamar a função id="btnVarinha" 'Reprocessar notas'

# AJUSTE
- ajuste os itens abaixo, alteração do que mudamos em cima:
- id="volumeFaixa" em 80
- id="volumeSint" em 85
- id="ataque" em 0,07
- id="sustain" em 1,8

- no thumbnail, adicione ao lado do tom a classificação vocal (genero e faixa vocal)


# AJUSTES
- quando mudo o timbre os valores abaixo são redefinidos para outros que eu não atualizei, como se o cache não fosse mantido
-- id="volumeFaixa" em 80
-- id="volumeSint" em 85
-- id="ataque" em 0,07
-- id="sustain" em 1,8
-- id="reverbNotas" em 10%
-- id="chorusNotas" em 15%

- alerta
-- quando pressionar qqr botão p gerar video (ex: id="bib-01950c03-video-padrao" ou id="bib-ed9cec10-video-instagram") e id="faixa-vocals-celula-audio" estiver marcado deve ter um alerta pedindo confirmação se quer seguir assim

# AUTOMAÇÕES
- ao lado de id="b5e07d" crie outro grupo com a label 'FLUXOS'
- crie um prieiro botão com o logo do youtube que ao clicar:
-- id="faixa-vocals-celula-audio" estiver marcado deve ter um alerta pedindo confirmação se quer seguir assim
-- gera o video do youtube com a thumbnail (igual botão id="bib-01950c03-video-padrao", por exemplo)
-- na sequencia publica no youtube o video selecioado id="seletorMusica"

# ANALYTICS
-  analytics ainda não está funcionando muito bem
- Coleta finalizada! 49 arquivos em analytics\ (31 consulta(s) recusada(s); veja leia-me.txt) (C:\Users\cs385499\PycharmProjects\TelaCifras\gerar_tablatura\analytics)
- id="estAnalise" não atualiza a data depois de pressionar id="btnEstAtualizar"
- não entendi a diferença entre id="btnEstAtualizar" e id="btnAnalytics". se tiverem o mesmo objetivo deixar apenas id="btnEstAtualizar"

- esse grafico id="a3c9f5" vem tudo como outros, embora no site do youtube exista a informação separada
