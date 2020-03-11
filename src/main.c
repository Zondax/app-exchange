/*******************************************************************************
*   Ledger Blue
*   (c) 2016 Ledger
*
*  Licensed under the Apache License, Version 2.0 (the "License");
*  you may not use this file except in compliance with the License.
*  You may obtain a copy of the License at
*
*      http://www.apache.org/licenses/LICENSE-2.0
*
*  Unless required by applicable law or agreed to in writing, software
*  distributed under the License is distributed on an "AS IS" BASIS,
*  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
*  See the License for the specific language governing permissions and
*  limitations under the License.
********************************************************************************/

#include "init.h"
#include "menu.h"
#include "swap_app_context.h"
#include "commands.h"
#include "power_ble.h"
#include "command_dispatcher.h"
#include "apdu_offsets.h"
#include "ux.h"

#include "usbd_core.h"
#define CLA 0xE0

unsigned char G_io_seproxyhal_spi_buffer[IO_SEPROXYHAL_BUFFER_SIZE_B];
swap_app_context_t ctx;

// recv()
// send()
// recv()
// UI
// recv(ASYNC)
//   send()->io_exchange(RETURN)  
// recv()
//
//             READY         RECEIVED          WAITING_USER
// recv()   to Received  ASYNC+to waiting          ERROR
// send()      ERROR         to ready      RETURN_AFTER_RX + to ready

typedef enum io_state {
    READY,
    RECEIVED,
    WAITING_USER
} io_state_e;

int output_length = 0;
io_state_e io_state = READY;

int recv_apdu() {
    PRINTF("Im inside recv_apdu\n");
    switch (io_state) {
        case READY:
            PRINTF("In state READY\n");
            io_state = RECEIVED;
            return io_exchange(CHANNEL_APDU, output_length);
        case RECEIVED:
            PRINTF("In state RECEIVED\n");
            io_state = WAITING_USER;
            return io_exchange(CHANNEL_APDU | IO_ASYNCH_REPLY, output_length);
        case WAITING_USER:
            PRINTF("Error: Unexpected recv call in WAITING_USER state\n");
            io_state = READY;
            return -1;
    };
    PRINTF("ERROR unknown state\n");
    return -1;
}

// return -1 in case of error
int send_apdu(unsigned char* buffer, unsigned int buffer_length) {
    os_memmove(G_io_apdu_buffer, buffer, buffer_length);
    output_length = buffer_length;
    PRINTF("Sending apdu\n");
    switch (io_state) {
        case READY:
            PRINTF("Error: Unexpected send call in READY state\n");
            return -1;
        case RECEIVED:
            io_state = READY;
            return 0;
        case WAITING_USER:
            PRINTF("Sending reply with IO_RETURN_AFTER_TX\n");
            io_exchange(CHANNEL_APDU | IO_RETURN_AFTER_TX, output_length);
            output_length = 0;
            io_state = READY;
            return 0;
    }
    PRINTF("Error: Unknown io_state\n");
    return -1;
}

void app_main(void) {
    int input_length = 0;
    init_application_context(&ctx);

    ui_idle();

    output_length = 0;
    io_state = READY;
    for(;;) {
        input_length = recv_apdu();
        PRINTF("I have received %d bytes\n", input_length);
        if (input_length == -1) // there were an error, lets start from the beginning
            return;
        if (input_length <= OFFSET_INS ||
            G_io_apdu_buffer[OFFSET_CLA] != CLA ||
            G_io_apdu_buffer[OFFSET_INS] >= COMMAND_UPPER_BOUND) {
            PRINTF("Error: bad APDU\n");
            return;
        }
        
        if (dispatch_command(G_io_apdu_buffer[OFFSET_INS], &ctx, G_io_apdu_buffer + OFFSET_CDATA, input_length - OFFSET_CDATA, send_apdu) < 0)
            return; // some non recoverable error happened

        if (ctx.state == INITIAL_STATE) {
            ui_idle();
            {
                //TODO: REMOVE ME

                #include "currency_lib_calls.h"
                unsigned char app_config[1] = {0};
                unsigned char amount[1] = {0};
                create_payin_transaction(app_config, 0, "Bitcoin", amount, 1, "blablalba", "");
            }
        }
    }
}

void app_exit(void) {

    BEGIN_TRY_L(exit) {
        TRY_L(exit) {
            os_sched_exit(-1);
        }
        FINALLY_L(exit) {

        }
    }
    END_TRY_L(exit);
}

__attribute__((section(".boot"))) int main(int arg0) {
    // exit critical section
    __asm volatile("cpsie i");

    // ensure exception will work as planned
    os_boot();
    
    for (;;) {
        UX_INIT();

        BEGIN_TRY {
            TRY {
                io_seproxyhal_init();

                USB_power(0);
                USB_power(1);

                power_ble();
              
                app_main();
            }
            CATCH(EXCEPTION_IO_RESET) {
                // reset IO and UX before continuing
                CLOSE_TRY;
                continue;
            }
            CATCH_ALL {
                CLOSE_TRY;
                break;
            }
            FINALLY {
            }
        }
        END_TRY;
    }
    app_exit();
    return 0;
}
