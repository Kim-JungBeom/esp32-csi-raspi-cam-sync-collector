// csi_router_logger.c
//
// Design: CSI callback -> enqueue into FreeRTOS queue
//         capture()    -> dequeue from queue (FIFO)
//         -> guarantees in-order 1:1 matching even under continuous reception
//
// Memory: CSI_QUEUE_LEN(16) x sizeof(csi_item_t)(~520 bytes) = ~8KB
//
// Output format (parsed by csi_save.py):
//   CSI_DATA,<sample>,<rssi>,<val0> <val1> ... <valN>

#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "esp_log.h"
#include "esp_wifi.h"

#define CSI_BUF_MAX     256     // Sufficient for HT20
#define CSI_QUEUE_LEN   16      // 16-entry buffer (~8KB)

static const char *TAG = "CSI_ROUTER";

typedef struct {
    wifi_pkt_rx_ctrl_t rx_ctrl;
    bool               first_word_invalid;
    uint16_t           len;
    int8_t             buf[CSI_BUF_MAX];
} csi_item_t;

static QueueHandle_t s_csi_queue = NULL;
static bool          s_started   = false;

// ──────────────────────────────────────────────
//  Public API: called when UDP packet is received
//  Dequeues oldest CSI entry and prints it (FIFO)
// ──────────────────────────────────────────────
void csi_router_logger_capture(int sample)
{
    if (!s_started || !s_csi_queue) return;

    csi_item_t item;

    if (xQueueReceive(s_csi_queue, &item, 0) != pdTRUE) {
        ESP_LOGW(TAG, "Sample %d: no CSI available (queue empty)", sample);
        return;
    }

    printf("CSI_DATA,%d,%d,", sample, item.rx_ctrl.rssi);

    int start = item.first_word_invalid ? 4 : 0;
    int end   = (item.len > CSI_BUF_MAX) ? CSI_BUF_MAX : item.len;
    for (int i = start; i < end; i++) {
        printf("%d", (int)item.buf[i]);
        if (i != end - 1) printf(" ");
    }
    printf("\n");
    fflush(stdout);
}

// ──────────────────────────────────────────────
//  Wi-Fi CSI receive callback (ISR context)
// ──────────────────────────────────────────────
static void wifi_csi_rx_cb(void *ctx, wifi_csi_info_t *info)
{
    if (!info || !info->buf || info->len == 0) return;
    if (!s_csi_queue) return;

    // Filter by AP MAC (ec:da:3b:5b:00:1d)
    static const uint8_t ap_mac[6] = {0xec, 0xda, 0x3b, 0x5b, 0x00, 0x1d};
    if (memcmp(info->mac, ap_mac, 6) != 0) return;

    csi_item_t item = {0};
    item.rx_ctrl            = info->rx_ctrl;
    item.first_word_invalid = info->first_word_invalid;
    item.len = (info->len > CSI_BUF_MAX) ? CSI_BUF_MAX : info->len;
    memcpy(item.buf, info->buf, item.len);

    // If queue is full, drop oldest entry and insert new one
    if (xQueueSendFromISR(s_csi_queue, &item, NULL) != pdTRUE) {
        csi_item_t dummy;
        xQueueReceiveFromISR(s_csi_queue, &dummy, NULL);
        xQueueSendFromISR(s_csi_queue, &item, NULL);
    }
}

// ──────────────────────────────────────────────
//  Initialization (safe to call on each reconnect)
// ──────────────────────────────────────────────
void csi_router_logger_start(void)
{
    if (!s_started) {
        s_csi_queue = xQueueCreate(CSI_QUEUE_LEN, sizeof(csi_item_t));
        if (!s_csi_queue) {
            ESP_LOGE(TAG, "Queue creation failed (out of memory)");
            return;
        }
        s_started = true;
        ESP_LOGI(TAG, "Queue created (%d x %d bytes = %d bytes)",
                 CSI_QUEUE_LEN, (int)sizeof(csi_item_t),
                 (int)(CSI_QUEUE_LEN * sizeof(csi_item_t)));
    }

    // Flush queue on reconnect
    csi_item_t dummy;
    while (xQueueReceive(s_csi_queue, &dummy, 0) == pdTRUE) {}

    wifi_csi_config_t cfg = {
        .lltf_en           = false,
        .htltf_en          = true,
        .stbc_htltf2_en    = false,
        .ltf_merge_en      = false,
        .channel_filter_en = false,
    };

    esp_wifi_set_csi_rx_cb(wifi_csi_rx_cb, NULL);
    esp_wifi_set_csi_config(&cfg);

    esp_err_t err = esp_wifi_set_csi(true);
    ESP_LOGI(TAG, "CSI logger started. set_csi(true): %s", esp_err_to_name(err));
}
