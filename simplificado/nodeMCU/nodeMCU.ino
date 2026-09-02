// Tela de letras sincronizada via NodeMCU (ESP-12/ESP8266) - ver simplificado/spec_esp32.md
// (documento completo; o nome do arquivo ficou de um rascunho anterior com ESP32, mas o
// hardware escolhido e o NodeMCU ESP8266/ESP-12 - ver a nota no topo do spec).
//
// O ESP8266 cria a propria rede Wi-Fi (modo SoftAP) e serve:
//   GET  /            e /letras.html  -> data/letras.html (tela pra ligar no projetor/TV)
//   GET  /musicas.json                -> data/musicas.json (dataset gerado por gerar_letras.ps1)
//   POST /estado  { "titulo": "...", "linha": N } -> guarda o estado atual (mandado pelo celular)
//   GET  /estado                      -> devolve o estado atual guardado
//
// Bibliotecas necessarias (Library Manager do Arduino IDE): so ArduinoJson (ESP8266WiFi,
// ESP8266WebServer e LittleFS ja vem com o core esp8266/Arduino). Testado com ArduinoJson 7.x
// (API JsonDocument sem tamanho fixo). Placa no Boards Manager: "NodeMCU 1.0 (ESP-12E Module)".
//
// Como gravar a pasta data/ (letras.html + musicas.json) no LittleFS do ESP8266 - ISSO E
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
// como musicas.json e SO servido como arquivo estatico do LittleFS (nunca carregado inteiro na
// RAM/parseado pelo firmware - isso fica por conta do navegador), isso nao e um problema. Escolha
// no Boards Manager um esquema de particao/flash size que sobre espaco de FS suficiente pro
// musicas.json (algumas centenas de KB) + letras.html.

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
	aplicarCabecalhosCors();
	server.send(204);
}

void handleEstadoPost() {
	aplicarCabecalhosCors();

	if (!server.hasArg("plain")) {
		server.send(400, "application/json", "{\"ok\":false}");
		return;
	}

	JsonDocument doc;
	DeserializationError erro = deserializeJson(doc, server.arg("plain"));
	if (erro) {
		server.send(400, "application/json", "{\"ok\":false}");
		return;
	}

	estadoTitulo = doc["titulo"].as<String>();
	estadoLinha = doc["linha"].as<int>();

	server.send(200, "application/json", "{\"ok\":true}");
}

void handleEstadoGet() {
	aplicarCabecalhosCors();

	JsonDocument doc;
	doc["titulo"] = estadoTitulo;
	doc["linha"] = estadoLinha;

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

	server.on("/", HTTP_GET, handleLetrasHtml);
	server.on("/letras.html", HTTP_GET, handleLetrasHtml);
	server.on("/musicas.json", HTTP_GET, handleMusicasJson);

	server.on("/estado", HTTP_OPTIONS, handleEstadoOptions);
	server.on("/estado", HTTP_POST, handleEstadoPost);
	server.on("/estado", HTTP_GET, handleEstadoGet);

	server.begin();
	Serial.println("Servidor HTTP iniciado");
}

void loop() {
	server.handleClient();
}
