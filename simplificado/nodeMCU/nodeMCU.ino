// Tela de letras sincronizada via NodeMCU (ESP-12/ESP8266) - ver simplificado/spec_esp32.md
// (documento completo; o nome do arquivo ficou de um rascunho anterior com ESP32, mas o
// hardware escolhido e o NodeMCU ESP8266/ESP-12 - ver a nota no topo do spec).
//
// O ESP8266 cria a propria rede Wi-Fi (modo SoftAP) e serve:
//   GET  /            e /index.html   -> data/index.html (copia de telaCel.html, pro celular -
//                                         ver nota de wake lock abaixo sobre o porque disso)
//   GET  /letras.html                 -> data/letras.html (tela pra ligar no projetor/TV)
//   GET  /musicas.json                -> data/musicas.json (dataset gerado por gerar_letras.ps1)
//   POST /estado  { "titulo": "...", "linha": N } -> guarda o estado atual (mandado pelo celular)
//   GET  /estado                      -> devolve o estado atual guardado
//
// Por que o celular abre http://192.168.4.1/ em vez de um telaCel.html baixado localmente: o
// Chrome recusa navigator.wakeLock.request() (NotAllowedError) em paginas file://, entao a tela
// do celular apagava sozinha durante o play - servir como pagina http:// de verdade resolve isso
// e de quebra garante que o celular sempre ve a versao atual (sem depender de reenviar o arquivo
// toda vez que ele mudar).
//
// Bibliotecas necessarias (Library Manager do Arduino IDE): so ArduinoJson (ESP8266WiFi,
// ESP8266WebServer e LittleFS ja vem com o core esp8266/Arduino). Testado com ArduinoJson 7.x
// (API JsonDocument sem tamanho fixo). Placa no Boards Manager: "NodeMCU 1.0 (ESP-12E Module)".
//
// Como gravar a pasta data/ (index.html + letras.html + musicas.json) no LittleFS do ESP8266 - ISSO E
// SEPARADO do upload do firmware (.ino) em si:
//   - Arduino IDE: instale o plugin de upload de LittleFS pro core esp8266 (ex.:
//     "arduino-esp8266littlefs-plugin" ou o mais recente "arduino-littlefs-upload", conforme a
//     versao do IDE) e use "Tools > ESP8266 LittleFS Data Upload" (ou equivalente) com este
//     sketch aberto.
//   - PlatformIO: basta rodar `pio run --target uploadfs` na raiz do projeto (usa esta mesma
//     pasta data/ automaticamente).
// TODO de quem for gravar no hardware pela primeira vez: confirme qual das duas ferramentas esta
// disponivel e complete/ajuste este comentario com o passo a passo exato que funcionou.
//
// Memoria/flash: o ESP8266 tem bem menos RAM que um ESP32 (uns 80KB uteis, contra 320KB+), mas
// como musicas.json/index.html/letras.html sao SO servidos como arquivo estatico do LittleFS
// (nunca carregados inteiros na RAM/parseados pelo firmware - isso fica por conta do navegador),
// isso nao e um problema. Escolha no Boards Manager um esquema de particao/flash size que sobre
// espaco de FS suficiente: os tres arquivos juntos somam uns 650KB hoje (index.html - copia de
// telaCel.html - e o maior, ~200KB, crescendo conforme mais musicas forem adicionadas).

#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <LittleFS.h>
#include <ArduinoJson.h>

// SSID/senha da rede que o ESP8266 cria. Editar aqui se precisar trocar.
const char *AP_SSID = "CifrasIgreja";
const char *AP_SENHA = "cifras123";

ESP8266WebServer server(80);

String estadoTitulo = "";
int estadoLinha = 0;
bool estadoAguardando = true;

// ===== CORS =====
// O celular abre telaCel.html como arquivo local (ou de outra origem, fora da rede CifrasIgreja
// ate trocar de Wi-Fi), entao o POST /estado e uma chamada de origem cruzada. Como o corpo e
// JSON (Content-Type: application/json), o navegador manda um preflight OPTIONS antes do POST de
// verdade. Sem esses cabecalhos, TODA chamada do celular falharia em silencio (o fetch() do
// celular ja tem catch() best-effort - o problema e que o estado nunca chegaria no ESP8266).
void aplicarCabecalhosCors() {
	server.sendHeader("Access-Control-Allow-Origin", "*");
	server.sendHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
	server.sendHeader("Access-Control-Allow-Headers", "Content-Type");
}

void handleEstadoOptions() {
	Serial.println("---- OPTIONS /estado (preflight CORS) recebido ----");
	aplicarCabecalhosCors();
	server.send(204);
}

// DEBUG temporario: se o navegador do celular pedir algo que nenhuma rota acima bateu (ex.: um
// path diferente por engano), isso aparece aqui em vez de sumir em silencio.
void handleNaoEncontrado() {
	Serial.print("404: ");
	Serial.print(server.method() == HTTP_GET ? "GET " : server.method() == HTTP_POST ? "POST " : server.method() == HTTP_OPTIONS ? "OPTIONS " : "? ");
	Serial.println(server.uri());
	server.send(404, "text/plain", "nao encontrado");
}

void handleEstadoPost() {
	aplicarCabecalhosCors();

	// DEBUG temporario: tira depois de confirmar que o POST chega certo (ver spec_esp32.md).
	Serial.println("---- POST /estado recebido ----");

	if (!server.hasArg("plain")) {
		Serial.println("SEM corpo 'plain' (hasArg(\"plain\") == false)");
		server.send(400, "application/json", "{\"ok\":false}");
		return;
	}

	String corpo = server.arg("plain");
	Serial.print("Corpo recebido: ");
	Serial.println(corpo);

	JsonDocument doc;
	DeserializationError erro = deserializeJson(doc, corpo);
	if (erro) {
		Serial.print("Falha ao parsear JSON: ");
		Serial.println(erro.c_str());
		server.send(400, "application/json", "{\"ok\":false}");
		return;
	}

	estadoTitulo = doc["titulo"].as<String>();
	estadoLinha = doc["linha"].as<int>();
	estadoAguardando = doc["aguardando"].as<bool>();

	Serial.print("Estado atualizado: titulo=");
	Serial.print(estadoTitulo);
	Serial.print(" linha=");
	Serial.println(estadoLinha);

	server.send(200, "application/json", "{\"ok\":true}");
}

void handleEstadoGet() {
	aplicarCabecalhosCors();

	JsonDocument doc;
	doc["titulo"] = estadoTitulo;
	doc["linha"] = estadoLinha;
	doc["aguardando"] = estadoAguardando;

	String saida;
	serializeJson(doc, saida);
	server.send(200, "application/json", saida);
}

bool servirArquivo(const String &caminho, const char *tipo) {
	if (!LittleFS.exists(caminho)) return false;
	File arquivo = LittleFS.open(caminho, "r");
	server.streamFile(arquivo, tipo);
	arquivo.close();
	return true;
}

void handleLetrasHtml() {
	if (!servirArquivo("/letras.html", "text/html; charset=utf-8")) {
		server.send(404, "text/plain", "letras.html nao encontrado no LittleFS");
	}
}

// GET / e GET /index.html servem o telaCel.html (copiado pelo gerar_letras.ps1 como index.html).
// Abrir via http://192.168.4.1/ em vez de um arquivo local resolve o navigator.wakeLock, que o
// Chrome recusa em paginas file:// (ver spec_esp32.md) - e elimina o risco de o celular estar
// com uma copia desatualizada, ja que sempre busca a versao que esta no proprio NodeMCU.
void handleIndexHtml() {
	if (!servirArquivo("/index.html", "text/html; charset=utf-8")) {
		server.send(404, "text/plain", "index.html nao encontrado no LittleFS");
	}
}

void handleMusicasJson() {
	if (!servirArquivo("/musicas.json", "application/json; charset=utf-8")) {
		server.send(404, "text/plain", "musicas.json nao encontrado no LittleFS");
	}
}

void setup() {
	Serial.begin(115200);

	if (!LittleFS.begin()) {
		Serial.println("Falha ao montar LittleFS");
	}

	WiFi.mode(WIFI_AP);
	WiFi.softAP(AP_SSID, AP_SENHA);
	Serial.print("SoftAP iniciado, IP: ");
	Serial.println(WiFi.softAPIP()); // deve ser 192.168.4.1

	server.on("/", HTTP_GET, handleIndexHtml);
	server.on("/index.html", HTTP_GET, handleIndexHtml);
	server.on("/letras.html", HTTP_GET, handleLetrasHtml);
	server.on("/musicas.json", HTTP_GET, handleMusicasJson);

	server.on("/estado", HTTP_OPTIONS, handleEstadoOptions);
	server.on("/estado", HTTP_POST, handleEstadoPost);
	server.on("/estado", HTTP_GET, handleEstadoGet);

	server.onNotFound(handleNaoEncontrado);

	server.begin();
	Serial.println("Servidor HTTP iniciado");
}

void loop() {
	server.handleClient();
}
