// ap_main.c
// AP slave: receives RPi trigger -> sends one UDP packet
//
// GPIO wiring:
//   GPIO14 (IN) <- RPi BCM17 (OUT) : capture complete + UDP send signal
//
// AP <-> Station : WiFi UDP
//   port 3333 : AP -> Station one packet (CSI measurement source)

#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "esp_netif.h"
#include "lwip/sockets.h"
#include "esp_private/wifi.h"
#include "driver/gpio.h"

static const char *TAG = "AP";

// ──────────────────────────────────────────────
//  Wi-Fi configuration
// ──────────────────────────────────────────────
#define AP_SSID         "CSI_TEST_AP"
#define AP_PASS         "12345678"
#define AP_CH           1
#define UDP_PORT        3333
#define STATION_IP      "192.168.4.2"

// ──────────────────────────────────────────────
//  GPIO pin
// ──────────────────────────────────────────────
#define GPIO_RPI_TRIGGER    GPIO_NUM_17  // <- RPi BCM17

// ──────────────────────────────────────────────
//  Global state
// ──────────────────────────────────────────────
static SemaphoreHandle_t s_trigger_sem = NULL;
static int               s_sample_num = 0;

// ──────────────────────────────────────────────
//  GPIO ISR: receives RPi trigger
// ──────────────────────────────────────────────
static void IRAM_ATTR gpio_isr_handler(void *arg)
{
    BaseType_t xHigher = pdFALSE;
    xSemaphoreGiveFromISR(s_trigger_sem, &xHigher);
    if (xHigher) portYIELD_FROM_ISR();
}

static void init_gpio(void)
{
    gpio_config_t io = {};
    io.intr_type    = GPIO_INTR_POSEDGE;
    io.mode         = GPIO_MODE_INPUT;
    io.pull_down_en = 1;
    io.pull_up_en   = 0;
    io.pin_bit_mask = (1ULL << GPIO_RPI_TRIGGER);
    gpio_config(&io);

    gpio_install_isr_service(0);
    gpio_isr_handler_add(GPIO_RPI_TRIGGER, gpio_isr_handler, NULL);
}

// ──────────────────────────────────────────────
//  UDP send task: waits for trigger -> sends one packet
// ──────────────────────────────────────────────
static void udp_send_task(void *arg)
{
    // Create socket after WiFi init (creating in app_main risks lwIP not ready crash)
    int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (sock < 0) {
        ESP_LOGE(TAG, "Socket creation failed");
        vTaskDelete(NULL);
        return;
    }

    struct sockaddr_in dest = {
        .sin_family      = AF_INET,
        .sin_port        = htons(UDP_PORT),
        .sin_addr.s_addr = inet_addr(STATION_IP),
    };

    char payload[200];
    memset(payload, 'X', sizeof(payload));
    memcpy(payload, "CSI_TRIGGER_PACKET", strlen("CSI_TRIGGER_PACKET"));

    ESP_LOGI(TAG, "Waiting for RPi trigger...");

    while (1) {
        if (xSemaphoreTake(s_trigger_sem, portMAX_DELAY) != pdTRUE) continue;

        s_sample_num++;

        sendto(sock, payload, sizeof(payload), 0,
               (struct sockaddr *)&dest, sizeof(dest));

        ESP_LOGI(TAG, "Sample %d: UDP sent", s_sample_num);
    }

    close(sock);
    vTaskDelete(NULL);
}

// ──────────────────────────────────────────────
//  SoftAP initialization
// ──────────────────────────────────────────────
static void wifi_init_softap(void)
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_ap();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    cfg.ampdu_tx_enable = 0;
    cfg.ampdu_rx_enable = 0;
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    wifi_config_t ap_cfg = {0};
    strncpy((char *)ap_cfg.ap.ssid,     AP_SSID, sizeof(ap_cfg.ap.ssid));
    strncpy((char *)ap_cfg.ap.password, AP_PASS,  sizeof(ap_cfg.ap.password));
    ap_cfg.ap.ssid_len        = strlen(AP_SSID);
    ap_cfg.ap.channel         = AP_CH;
    ap_cfg.ap.max_connection  = 4;
    ap_cfg.ap.authmode        = WIFI_AUTH_WPA2_PSK;
    ap_cfg.ap.beacon_interval = 100;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &ap_cfg));
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_bandwidth(WIFI_IF_AP, WIFI_BW_HT20));
    ESP_ERROR_CHECK(esp_wifi_internal_set_fix_rate(
        WIFI_IF_AP, true, WIFI_PHY_RATE_MCS0_LGI));

    ESP_LOGI(TAG, "SoftAP started. SSID=%s CH=%d", AP_SSID, AP_CH);
}

// ──────────────────────────────────────────────
//  app_main
// ──────────────────────────────────────────────
void app_main(void)
{
    ESP_ERROR_CHECK(nvs_flash_init());

    s_trigger_sem = xSemaphoreCreateBinary();

    wifi_init_softap();
    init_gpio();

    xTaskCreate(udp_send_task, "udp_send", 4096, NULL, 5, NULL);

    ESP_LOGI(TAG, "AP ready. Waiting for RPi trigger...");
}
