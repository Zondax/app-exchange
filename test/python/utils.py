from pathlib import Path
from time import sleep

def handle_lib_call_start_or_stop(backend):
    # Give some time to actually start the new app
    sleep(1)

    # The USB stack will be reset by the called app
    backend.handle_usb_reset()


def int_to_minimally_sized_bytes(n: int) -> bytes:
    return n.to_bytes((n.bit_length() + 7) // 8, 'big') or b'\0' # case n is 0
