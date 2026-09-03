# SPEC: Tela de letras sincronizada via ESP32/NodeMCU

> Este documento é a especificação completa de uma funcionalidade a ser implementada no projeto `TelaCifras/simplificado`. Foi escrito para ser lido do zero, em outra máquina/sessão, sem contexto prévio da conversa que o originou. Se você (Claude) está lendo isso agora: leia o documento inteiro antes de tocar em qualquer arquivo, e leia os arquivos-fonte citados (especialmente `telaCel.html`) para confirmar que o código ainda corresponde ao que está descrito aqui — pode ter mudado desde que este documento foi escrito.
>
> **Nota de hardware**: a primeira versão deste spec partia de ESP32 (daí o nome do arquivo e menções que possam ter sobrado). O usuário corrigiu isso: o hardware real é um **NodeMCU ESP-12 (ESP8266)** que ele já tem em mãos. O documento foi atualizado pra refletir isso (seção 3.1), incluindo os arquivos/pastas já implementados em `simplificado/nodeMCU/`. Se algo neste documento ainda mencionar ESP32 fora da seção 3.1, é sobra que escapou da revisão — confira contra o código antes de confiar.

## 1. Contexto do projeto

`simplificado/` é uma ferramenta para visualizar cifras (letra + acordes) de músicas no celular, feita a partir de `app.html` (um app maior e mais completo que vive na raiz do repositório). Fluxo atual:

1. `extrai.bat` → `extrai.ps1`: lê `app.html`, extrai a tag `<musicas>`, e cria um arquivo `.txt` por música dentro de `\cifras`. Cada `.txt` tem: linha 1 = título, linha 2 = `TOM:<tom>`, duas linhas em branco, depois o corpo da cifra (acordes + letra intercalados, texto puro).
2. `inclui.bat` → `inclui.ps1`: lê todos os `.txt` de `\cifras` e monta `telaCel.html`, substituindo o bloco `<musicas>...</musicas>` (um `<script type="application/xml">`) por um `<musica><![CDATA[ ...conteúdo completo do .txt... ]]></musica>` por música. A primeira linha de cada `<musica>` é o título.
3. `telaCel.html` é o app em si — uma página HTML/CSS/JS única (sem frameworks, sem build step) pensada pra ser aberta no navegador do celular. Roda 100% client-side.

### 1.1 O que `telaCel.html` já faz (não precisa reimplementar, só reaproveitar)

Tudo isso vive dentro de uma única IIFE `(function () { "use strict"; ... })();` no `<script>` final do arquivo:

- **Parse dos dados**: lê o XML embutido (`#musicas-xml`), monta um array `musicas` = `[{ titulo, conteudo, semis, velocidade }, ...]`, ordenado alfabeticamente (função `normalizar` faz o fold de acentos pra comparação).
- **Identificação de cifra vs letra**: `CHORD_TOKEN_RE`, `isChordToken(tok)`, `isChordLine(line)` — uma linha é "de acordes" se todos os tokens (ou ≥50% com pelo menos 2) baterem no regex de acorde. **Esta é a função-chave para separar letra de cifra** — reaproveite exatamente essa lógica (ou uma porta fiel dela) em qualquer script novo que precise saber se uma linha é acorde ou letra.
- **Coloração/render**: `renderCifraLinha`, `renderCifra` — colore acordes (`#f60`) e letra (`#fff`), aplica transposição.
- **Quebra de linha longa**: `quebrarLinhasLongas`, `quebrarPar`, `quebrarLinhaSolta`, `medirColunasDisponiveis` — quebra pares cifra+letra na mesma coluna quando não cabem na tela. **Isso só existe para exibição visual; não é relevante para a sincronização (a sincronização deve trabalhar com as linhas originais, não as quebradas — ver seção 4).**
- **Transposição**: `transporAtual(delta)`, ligado aos botões "+"/"-" do menu lateral, persiste em `localStorage["cifras_transpostos_v1"]` (mapa `{titulo: semitons}`).
- **Menu lateral alfabético**: `#nav-alfabeto`, letras A-Z que rolam até a primeira música daquela inicial (`primeiraPorLetra`).
- **Detecção de "música atual"**: `musicaNaAltura(y)` — dado um Y de referência na tela, acha a última seção `.musica` visível (`!s.hidden`) cujo topo já passou desse Y, ordenando por posição real (`getBoundingClientRect().top`) e não pela ordem do DOM (importante pois o filtro de seleção reordena visualmente via CSS `order`). Duas variações já prontas:
  - `musicaAtual()` — referência = fundo do `<h1>` fixo no topo. Usada pelo transpor.
  - `musicaSobPlay()` — referência = topo do botão de play flutuante. Usada pra saber a velocidade de rolagem.
- **Rolagem automática (play/pause)**: slider de velocidade (0-100%, por música, salvo em `localStorage["cifras_velocidades_v1"]`) abaixo do `<h2>` de cada música. Botão flutuante `#play-pause-btn` (ícone Bootstrap Icons `bi-play`/`bi-pause`, alpha 0.6). Fórmula atual: `pxPorSegundo(pct) = pct * 0.5` (cada 1% = 0.5px/s). Usa `requestAnimationFrame` com acumulador fracionário (`fracaoAcumulada`) pra não perder velocidades baixas por arredondamento do `scrollBy`.
- **Seleção e filtro de músicas**: clicar no `<h2>` alterna classe `.selecionada` (cor `#f60`), array `ordemSelecao` (ordem de clique, não alfabética) salvo em `localStorage["cifras_selecionadas_v1"]`. Com ≥1 selecionada, aparecem `#filtro-btn` (funil) e `#limpar-selecao-btn` (x) do lado do play. Filtro usa CSS `order` em `#lista-musicas` (que é `display:flex; flex-direction:column`) pra reordenar sem mover nós no DOM.
- **Wake Lock**: `navigator.wakeLock.request("screen")` ao iniciar rolagem, liberado ao pausar, reconquistado em `visibilitychange` se ainda estiver tocando.

Todas essas funções vivem no MESMO escopo (a IIFE), então uma função nova adicionada ali pode chamar `musicas`, `isChordLine`, `musicaAtual`, etc. diretamente.

## 2. Objetivo desta funcionalidade

O usuário (Rafael) toca/lidera cânticos na igreja usando o celular com `telaCel.html`. Ele quer que a **letra** (sem cifra) da música que está aparecendo na tela do celular apareça **também** numa tela/projetor ligado a um **computador da igreja**, para a congregação ler e cantar junto.

## 3. Restrições confirmadas (não são hipóteses, foram checadas com o usuário)

- **Não é permitido instalar nada no computador da igreja.** Ele só pode abrir o navegador que já existe e digitar um endereço.
- **Não há servidor externo/de terceiros disponível** (nada de Firebase, serviços pagos, hospedagem na nuvem). Tudo tem que rodar localmente.
- **Há Wi-Fi disponível no local**, mas a configuração da rede da igreja é desconhecida/não confiável — pode ter "isolamento de cliente" (clientes não se enxergam, só o roteador/internet), o que quebraria qualquer solução que dependa de dois aparelhos conversando diretamente na rede da igreja.
- O usuário vai usar um **NodeMCU ESP-12 (ESP8266)** que já tem disponível, conectado via USB (porta COM identificada na máquina onde for gravar) — ver seção 3.1. (Uma versão anterior deste documento partia de ESP32; o nome do arquivo ficou assim, mas o hardware da decisão atual é o NodeMCU/ESP8266.)
- O celular é do usuário — pode instalar/configurar o que for preciso nele.
- A implementação será feita **em outra máquina**, sem acesso a esta conversa — por isso este documento precisa ser autossuficiente.

### 3.1 Por que NodeMCU ESP8266/ESP-12 (decisão do usuário, corrigindo uma versão anterior deste documento que partia de ESP32)

- O usuário já tem a placa em mãos — não precisa comprar/esperar nada.
- Mesmo sem o RAM/flash mais folgados de um ESP32, isso não é um problema real aqui: `musicas.json` é servido como arquivo estático do LittleFS (nunca é carregado inteiro nem parseado pelo firmware — quem parseia é o navegador), e o firmware só precisa parsear o corpo pequeno do `POST /estado` ({titulo, linha}). Escolher um esquema de partição/flash size com espaço de FS suficiente (algumas centenas de KB) no Boards Manager resolve.
- Sem Bluetooth (ao contrário do ESP32) — mas BLE era só um *fallback* de v2 (ver seção 8), nunca foi requisito do v1.
- Para resolver o risco de isolamento de cliente na rede da igreja, **o NodeMCU cria sua própria rede Wi-Fi (modo Access Point)** em vez de entrar na rede da igreja. Celular e computador da igreja conectam nessa rede do NodeMCU (troca manual de Wi-Fi antes do culto). Isso elimina a dependência da configuração da rede da igreja por completo.
- IP fixo e conhecido: no modo AP do Arduino/ESP8266, o IP do próprio ESP é sempre `192.168.4.1` por padrão — não precisa de mDNS nem descoberta de IP.
- Bibliotecas: núcleo Arduino-ESP8266 usa `ESP8266WiFi.h`/`ESP8266WebServer.h` (em vez de `WiFi.h`/`WebServer.h` do ESP32) e `LittleFS.h` (API quase idêntica, mas `LittleFS.begin()` no ESP8266 não recebe o parâmetro booleano de formatar-se-falhar que o ESP32 aceita). A API do `ESP8266WebServer` é a mesma do `WebServer` do ESP32 pros metodos usados aqui (`on`, `send`, `sendHeader`, `streamFile`, `hasArg`/`arg("plain")`, incluindo `HTTP_OPTIONS`) — o código muda pouco entre as duas placas.

## 4. Arquitetura e contrato de dados

```
┌─────────────┐   Wi-Fi (rede do NodeMCU, SoftAP) ┌──────────────┐   Wi-Fi (mesma rede)   ┌──────────────────┐
│  Celular     │ ◄──── GET /  (index.html) ──────  │   NodeMCU    │ ◄──── GET /estado ──── │  PC da igreja     │
│  (navegador) │ ───── POST /estado (JSON) ──────► │(ESP8266WebSrv)│ ──── GET /letras.html ►│  (só navegador)   │
└─────────────┘                                    └──────────────┘                        └──────────────────┘
```

- O NodeMCU é o servidor. Ele guarda em memória o "estado atual" (última música/linha recebida do celular) e serve isso sob demanda pro navegador da igreja.
- **O próprio NodeMCU serve o `telaCel.html` pro celular** (copiado como `index.html`, ver seção 5.1/5.2) — o celular abre `http://192.168.4.1/` no navegador em vez de um arquivo baixado localmente. Motivo (achado na prática, não é só preferência): `navigator.wakeLock.request()` (usado pra impedir a tela do celular de apagar durante o play) lança `NotAllowedError` em páginas `file://` — o Chrome recusa a permissão nesse tipo de origem, mesmo sendo tecnicamente um "contexto seguro". Servir como página `http://` de verdade resolve isso, e de quebra elimina o risco de o celular estar com uma cópia desatualizada do arquivo (problema real que já aconteceu — ver seção 5.5 sobre a URL relativa `/estado`).
- O celular manda updates (fire-and-forget, best-effort) sempre que a linha/música visível na tela mudar.
- O navegador da igreja fica com `letras.html` (servido pelo próprio NodeMCU) aberto, dando **polling** em `/estado` a cada ~1s e atualizando o destaque/scroll conforme o valor mudar.
- **v1 é só HTTP + polling (sem WebSocket)** — sem dependências externas de biblioteca, só `ESP8266WiFi.h` + `ESP8266WebServer.h` (core padrão do Arduino-ESP8266). WebSocket é uma melhoria de v2 (seção 8), não bloqueia o v1.
- Toda comunicação do celular pro NodeMCU deve ser **best-effort e não-bloqueante**: se o NodeMCU estiver desligado/fora de alcance, `telaCel.html` deve continuar funcionando normalmente (sem travar, sem mostrar erro pro usuário). Use `fetch(...).catch(() => {})` com um timeout curto (ex.: `AbortController` com ~1.5s).
- **CORS (achado durante a implementação, não é opcional)**: quando `telaCel.html` é aberto como arquivo local (uso standalone, sem NodeMCU, via o botão de download) o `POST /estado` é uma chamada de **origem cruzada**. Como o corpo é `application/json`, o navegador manda um *preflight* `OPTIONS` antes do POST de verdade. Sem o servidor responder esse preflight com os cabeçalhos CORS certos, **toda** atualização falha em silêncio — o `catch()` best-effort do celular esconde o erro, então o sintoma é só "a tela da igreja nunca atualiza", sem nenhuma pista no console. O firmware (seção 5.2) precisa tratar `OPTIONS /estado` explicitamente e mandar `Access-Control-Allow-Origin: *` em toda resposta de `/estado` — isso continua necessário mesmo no modo "servido pelo NodeMCU" (`/estado` relativo é mesma origem e não dispara preflight, mas o modo arquivo local ainda existe e usa o IP fixo com CORS).

### 4.1 Identificação de linha — a peça mais importante do contrato

O objetivo é que o celular e o NodeMCU concordem sobre "qual linha é a linha N da música X", **sem precisar reimplementar a lógica de quebra de linha visual** (que é só cosmética e depende da largura da tela de cada dispositivo, então não pode ser a base do índice).

**Regra**: o índice de linha é sempre relativo ao corpo **original, não quebrado** do arquivo `.txt` da música (o mesmo texto que fica dentro do `<![CDATA[ ]]>` no `telaCel.html`, sem a primeira linha que é o título). Ou seja:

```js
var linhasOriginais = musica.conteudo.split(/\r?\n/); // JÁ é isso — telaCel.html usa exatamente essa variável internamente pra montar "corpo"
```

Cada linha nesse array tem um índice fixo (0, 1, 2, ...) que **não muda** independente de quebra de linha visual, tamanho de tela, zoom, etc. Esse índice é o que trafega entre celular e NodeMCU.

### 4.2 Dataset de letras no NodeMCU

O NodeMCU precisa ter, para cada música, a lista de linhas originais **marcadas** como `"acorde"` ou `"letra"` (usando a mesma lógica de `isChordLine`), pra poder renderizar só a letra em `letras.html` mas ainda indexar pela linha original completa (índices não podem "pular" as linhas de acorde, senão o celular e o NodeMCU ficam com numeração diferente).

Formato do dataset (arquivo `musicas.json`, ver seção 5.1 para como gerá-lo):

```json
[
  {
    "titulo": "Oceanos",
    "linhas": [
      { "tipo": "letra", "texto": "" },
      { "tipo": "acorde", "texto": "Bm" },
      { "tipo": "letra", "texto": "" },
      { "tipo": "acorde", "texto": "Bm                   A/C#    D" },
      { "tipo": "letra", "texto": "   Tua voz me chama sobre as águas" },
      ...
    ]
  },
  ...
]
```

- `linhas` é o array completo (acorde E letra, na ordem original), pra manter os índices batendo com o celular.
- `letras.html` ao renderizar, **pula** (não desenha) as linhas com `tipo: "acorde"`, mas mantém a contagem de índice intacta ao procurar/rolar até um índice recebido.

### 4.3 Mensagem celular → NodeMCU

`POST /estado`, corpo JSON:

```json
{ "titulo": "Oceanos", "linha": 4 }
```

- `titulo`: exatamente igual ao título usado no dataset (`musica.titulo` do `telaCel.html`).
- `linha`: índice (0-based) da linha original que está **no topo da área visível** da cifra na tela do celular (ver seção 4.4 para como calcular).
- Debounce: não enviar a cada pixel de scroll — envie no máximo 1x a cada ~300ms, e só quando o valor (`titulo`+`linha`) realmente mudou desde o último envio.

O NodeMCU responde `200 OK` (corpo vazio ou `{"ok":true}`) e guarda esse par em duas variáveis globais (`String estadoTitulo`, `int estadoLinha`).

### 4.4 Como o celular calcula a `linha` atual

Isso é uma função **nova** a ser adicionada em `telaCel.html`, reaproveitando o padrão de `musicaNaAltura`/`musicaSobPlay` já existente:

1. Ache a música atualmente visível (pode reaproveitar `musicaAtual()` — referência = topo da área de conteúdo, abaixo do `<h1>` fixo).
2. Dentro do `<pre class="cifra">` dessa música, cada linha renderizada (span/linha de texto) precisa carregar consigo o índice da linha **original** de onde veio — mesmo depois de quebrada. Isso exige uma pequena mudança em `renderCifra`/`renderCifraLinha`/`quebrarLinhasLongas`: ao invés de só devolver strings de HTML, cada linha (ou pedaço de linha, se foi quebrada) deve carregar um atributo `data-linha-original="N"` no `<span class="linha">` (ou equivalente) que a envolve. Todos os pedaços de uma linha quebrada em 2+ carregam o MESMO `N` (o índice da linha antes de quebrar).
3. Com isso, achar "qual `data-linha-original` está no topo da área visível" é o mesmo tipo de busca geométrica que `musicaNaAltura` já faz, só que aplicada aos elementos de linha dentro do `<pre>` em vez de às seções `.musica`.
4. Envie isso (com debounce) via `fetch("http://192.168.4.1/estado", { method: "POST", body: JSON.stringify({titulo, linha}), headers: {"Content-Type": "application/json"} })`, com timeout curto e `.catch()` silencioso.
5. Isso deve rodar **sempre** (não só quando a rolagem automática estiver ativa) — o usuário pode estar rolando manualmente com o dedo, e a tela da igreja deve acompanhar do mesmo jeito. Dispare a checagem em um listener de `scroll` (com debounce/throttle, ex. `requestAnimationFrame` ou `setTimeout` de ~200ms) no `window`.
6. O IP do NodeMCU (`192.168.4.1` por padrão no modo AP) deve ser configurável (não hardcoded sem alternativa), pra caso o modo AP mude no futuro. Sugestão simples: uma constante no topo do script, ou um campo salvo em `localStorage` com valor padrão `192.168.4.1`. (Implementado como a constante `SERVIDOR_IP` no topo da seção de sincronização de `telaCel.html`.)

### 4.5 `GET /estado` (NodeMCU → navegador da igreja)

Resposta JSON:

```json
{ "titulo": "Oceanos", "linha": 4 }
```

`letras.html` faz polling disso a cada ~1s. Ao detectar mudança de `titulo`, troca de música (rola até o topo dela). Ao detectar mudança de `linha` (mesmo título), rola suavemente até aquela linha (pode ficar no topo da tela, ou centralizada — escolha razoável de UX, não é crítico). Sugestão: destacar (ex. fundo levemente diferente) as ~3-5 linhas de letra ao redor da linha atual, pra ficar fácil de achar visualmente onde a congregação deve estar cantando.

## 5. Componentes a implementar

### 5.1 Script de extração do dataset de letras (novo)

**Objetivo**: gerar `musicas.json` (formato da seção 4.2) a partir de `simplificado/cifras/*.txt` — a mesma fonte de dados que `inclui.ps1` já usa.

- Sugestão de nome: `simplificado/gerar_letras.ps1` (mesmo padrão dos scripts existentes: `extrai.ps1`, `inclui.ps1`).
- Precisa reimplementar (em PowerShell) a mesma lógica de `isChordLine`/`isChordToken`/`CHORD_TOKEN_RE` que já existe em JS dentro de `telaCel.html` — **copie a regex e as regras exatamente**, para que a classificação bata 100% com o que o próprio `telaCel.html` mostra colorido (senão uma linha pode aparecer como "acorde" pro celular e "letra" pro NodeMCU, ou vice-versa, e os índices/exibição ficam inconsistentes entre os dois lados). **Cuidado com encoding**: caracteres como "º"/"°" em símbolos de acorde (ex.: "Ebº") precisam ser tratados via código Unicode (`[char]0x00BA`) em vez de literal no `.ps1`, senão o jeito como o Windows PowerShell 5.1 lê o próprio arquivo do script pode corromper esses caracteres e quebrar a classificação silenciosamente — valide sempre comparando a saída contra a lógica JS real (não contra uma releitura sua dela).
- Saída: `simplificado/nodeMCU/data/musicas.json` (ver seção 5.3 sobre a pasta `data/`).
- **Também copia `simplificado/telaCel.html` para `simplificado/nodeMCU/data/index.html`** — é essa cópia que o NodeMCU serve pro celular em `GET /` (ver seção 4 sobre o porquê: `navigator.wakeLock` não funciona em `file://`). Como isso é só uma cópia de arquivo (não regenera `telaCel.html`), rode `inclui.ps1` **antes** deste script se `\cifras` mudou, senão o `index.html` sai com conteúdo desatualizado.
- Deve rodar sob demanda (tipo `extrai.bat`/`inclui.bat`), não precisa de bat separado necessariamente — pode reaproveitar/estender `inclui.ps1` pra gerar os dois formatos (o XML do `telaCel.html` E o `musicas.json`) na mesma execução, já que ambos partem da mesma pasta `\cifras`. Decisão de implementação livre; só documentar no próprio script qual é a fonte e o destino.

### 5.2 Firmware do NodeMCU (novo)

- Localização: `simplificado/nodeMCU/nodeMCU.ino` (nome de pasta = nome do sketch, convenção do Arduino IDE; a pasta já existia como stub vazio antes deste spec).
- Placa no Boards Manager: "NodeMCU 1.0 (ESP-12E Module)".
- Bibliotecas: só as que já vêm com o core `esp8266` do Arduino (`ESP8266WiFi.h`, `ESP8266WebServer.h`, `LittleFS.h` para servir arquivos estáticos, `ArduinoJson` — **esta é uma dependência externa, mas é uma lib instalada no PC de desenvolvimento do usuário, não no computador da igreja, então não viola a restrição da seção 3**; usá-la é o jeito padrão/robusto de montar e parsear JSON no Arduino, evite escrever um parser JSON manual). A API do `ESP8266WebServer` é praticamente igual à do `WebServer` do ESP32 (mesma origem) — só muda o nome dos headers e da classe.
- Comportamento no `setup()`:
  1. Inicializa `LittleFS` (sistema de arquivos onde `letras.html` e `musicas.json` foram gravados via upload de dados do Arduino IDE — ver seção 5.3). No ESP8266, `LittleFS.begin()` não recebe parâmetro de formatar-se-falhar (diferente do ESP32).
  2. Sobe Wi-Fi em modo **SoftAP**: `WiFi.softAP("CifrasIgreja", "<senha a definir>")`. SSID e senha devem ficar em constantes fáceis de achar/editar no topo do arquivo.
  3. Registra rotas no `ESP8266WebServer`:
     - `GET /` e `GET /index.html` → serve `index.html` do `LittleFS` (cópia de `telaCel.html`, é o que o celular abre).
     - `GET /letras.html` → serve `letras.html` do `LittleFS` (é o que o computador da igreja abre).
     - `GET /musicas.json` → serve `musicas.json` do `LittleFS` (assim `letras.html` carrega o dataset completo via `fetch` normal, sem precisar embutir no HTML).
     - `OPTIONS /estado` → responde o preflight CORS (204 + cabeçalhos `Access-Control-Allow-*`, ver nota de CORS na seção 4).
     - `POST /estado` → lê o corpo (JSON), atualiza `estadoTitulo`/`estadoLinha` (variáveis globais), responde 200 (com os mesmos cabeçalhos CORS).
     - `GET /estado` → responde `{"titulo": estadoTitulo, "linha": estadoLinha}`.
  4. `server.begin()`.
- No `loop()`: só `server.handleClient()`.
- Sem necessidade de persistir estado entre reinícios (se o NodeMCU resetar, o celular vai mandar o estado atual de novo assim que o usuário rolar a tela).

### 5.3 Pasta de dados do NodeMCU (`data/`)

O Arduino IDE tem uma ferramenta (plugin de upload de LittleFS pro core esp8266, ex. "arduino-esp8266littlefs-plugin" ou o mais recente "arduino-littlefs-upload" conforme a versão do IDE, via `Tools > ESP8266 LittleFS Data Upload` ou equivalente) que grava o conteúdo de uma pasta `data/` (irmã do `.ino`) direto no `LittleFS` do NodeMCU, separado do upload do firmware em si. No PlatformIO é o comando equivalente. Estrutura esperada:

```
simplificado/nodeMCU/
├── nodeMCU.ino
└── data/
    ├── index.html    (copia de telaCel.html, gerada pelo script da secao 5.1)
    ├── letras.html
    └── musicas.json  (gerado pelo script da secao 5.1)
```

**Nota para quem for implementar**: confirme se está usando Arduino IDE (precisa instalar o plugin de upload de LittleFS compatível com a versão em uso) ou PlatformIO (já tem esse recurso embutido via `pio run --target uploadfs`) — o processo de upload da pasta `data/` muda de ferramenta pra ferramenta, documente o passo a passo escolhido dentro do próprio `nodeMCU.ino` como comentário no topo do arquivo. Escolha no Boards Manager um esquema de partição/flash size com espaço de FS suficiente — os três arquivos juntos somam uns 650KB hoje (`index.html` é o maior, crescendo conforme mais músicas forem adicionadas).

### 5.4 `letras.html` (novo)

Página estática (HTML+CSS+JS, sem framework, mesmo espírito de `telaCel.html`) que:

- No load, dá `fetch("/musicas.json")` e guarda os dados.
- Faz polling em `fetch("/estado")` a cada ~1s.
- Ao receber `{titulo, linha}`:
  - Se `titulo` mudou: monta a view daquela música (renderiza só as linhas com `tipo === "letra"`, pulando as de acorde, mas mantendo os elementos indexados por linha original via `data-linha-original`, do mesmo jeito que a seção 4.4 pede pro celular).
  - Rola/destaca a linha correspondente.
- Visual: tela cheia, fonte grande (é pra ser lida à distância, num projetor/TV — bem diferente do `telaCel.html`, que é pra tela pequena de celular). Pode reaproveitar a paleta de cores (fundo escuro `#1c1c1c`, letra `#fff`) só que com fonte bem maior (ex.: `3-5em`) e talvez sem cifra ocupando espaço nenhum (já que cifra nem é renderizada aqui).
- Deve indicar visualmente se perdeu conexão com o NodeMCU (polling falhando) — algo discreto, não precisa ser chamativo.

### 5.5 Alterações em `telaCel.html` (existente)

Resumo do que precisa mudar (detalhado na seção 4.4):

1. Em `renderCifra`/`renderCifraLinha` (e no que for necessário de `quebrarLinhasLongas`): carregar o índice da linha original em cada linha renderizada (`data-linha-original`).
2. Nova função de detecção de linha visível dentro da música atual (reaproveitando o padrão de `musicaNaAltura`).
3. Nova função de envio (`fetch` POST, debounced, best-effort, silenciosa em caso de erro).
4. Listener de `scroll` no `window` disparando essa detecção+envio (sempre ativo, não só durante auto-scroll).
5. Uma constante/config pro IP do NodeMCU (`192.168.4.1` como padrão — implementada como `SERVIDOR_IP`), usada só de fallback: quando `telaCel.html` é servido pelo próprio NodeMCU (`window.location.protocol !== "file:"`), usa caminho relativo `/estado` (mesma origem, funciona mesmo que o IP mude) — só cai pro IP fixo quando a página foi aberta como arquivo local (`file://`, modo standalone via o botão de download).

**Importante**: essas mudanças não podem quebrar nada do que já existe (transposição, filtro, rolagem automática, quebra de linha) nem degradar a experiência quando não há NodeMCU por perto — teste explicitamente o cenário "NodeMCU desligado" e confirme que `telaCel.html` continua 100% funcional e sem erros/lentidão perceptível no console.

## 6. Fluxo de uso esperado (ponta a ponta)

1. Em casa: roda `inclui.ps1` se `\cifras` mudou, depois `gerar_letras.ps1` (regenera `musicas.json` E copia `telaCel.html` para `nodeMCU/data/index.html`). Faz upload do firmware + pasta `data/` pro NodeMCU via Arduino IDE/PlatformIO (dois passos separados — ver seção 5.3).
2. Na igreja: liga o NodeMCU em qualquer USB (só energia — ver conversa que originou este documento, adaptador USB do NodeMCU NÃO dá acesso de rede por cabo, só energia/gravação). Ele sobe a rede Wi-Fi `CifrasIgreja`.
3. Celular conecta na rede `CifrasIgreja`, abre `http://192.168.4.1/` no navegador (é o próprio NodeMCU servindo `telaCel.html` — não mais um arquivo baixado localmente, ver seção 4 sobre o wake lock).
4. Computador da igreja conecta na rede `CifrasIgreja`, abre o navegador, digita `http://192.168.4.1/letras.html`.
5. Conforme o usuário rola/toca as músicas no celular (manual ou via play automático), a tela da igreja acompanha sozinha.

## 7. Critérios de aceite

- [ ] `musicas.json` gerado bate 100% (mesmos títulos, mesma classificação acorde/letra linha a linha) com o que `telaCel.html` já mostra colorido pra cada música.
- [ ] Com o NodeMCU desligado, `telaCel.html` funciona exatamente como funciona hoje (sem erros no console, sem trava, sem delay perceptível).
- [ ] Com o NodeMCU ligado e os três aparelhos na rede `CifrasIgreja`: rolar manualmente o celular atualiza `letras.html` em até ~1-2s. Trocar de música atualiza corretamente o título mostrado. **Testar especificamente com o celular numa origem diferente da do NodeMCU (ex.: arquivo local) — é o cenário real de uso, e é o que expõe o requisito de CORS da seção 4.**
- [ ] `letras.html` nunca mostra uma linha de acorde.
- [ ] Reiniciar o NodeMCU no meio do uso não trava nada (celular volta a mandar estado no próximo scroll; `letras.html` volta a receber assim que o servidor sobe de novo).
- [ ] Testado com pelo menos uma música que tenha linha quebrada (`quebrarLinhasLongas`) para confirmar que o índice de linha original continua correto mesmo com o texto quebrado visualmente em pedaços diferentes.

## 8. Fora de escopo do v1 (não implementar agora, só documentado para o futuro)

- **WebSocket** (via `ESPAsyncWebServer`/`AsyncWebSocket`) no lugar do polling, pra latência menor. Troca só o transporte; o contrato de dados (seção 4) continua o mesmo.
- **BLE como transporte alternativo/fallback**: o NodeMCU/ESP8266 clássico não tem Bluetooth (diferente do ESP32) — se isso vier a ser necessário no futuro, exigiria trocar de placa. Não é necessário pro v1 (Wi-Fi via SoftAP já resolve o problema de isolamento de rede).
- Múltiplos celulares/controladores mandando estado pro mesmo NodeMCU (hoje o design assume um único celular como fonte da verdade).
- Persistir o estado atual em flash (sobrevivendo a reset do NodeMCU) — não é necessário, ver critério de aceite sobre reinício.
