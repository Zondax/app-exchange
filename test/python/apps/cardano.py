from enum import IntEnum

from hashlib import sha512
from ecdsa.curves import Ed25519
from ecdsa.keys import VerifyingKey

from ragger.backend.interface import BackendInterface
from ragger.bip import pack_derivation_path, calculate_public_key_and_chaincode, CurveChoice
from ragger.utils import create_currency_config


ADA_CONF = create_currency_config("ADA", "Cardano ADA")

ADA_BYRON_DERIVATION_PATH = "m/44'/1815'/0'/0/0"
ADA_SHELLEY_DERIVATION_PATH = "m/1852'/1815'/0'/0/0"
ADA_BYRON_PACKED_DERIVATION_PATH = pack_derivation_path(ADA_BYRON_DERIVATION_PATH)
ADA_SHELLEY_PACKED_DERIVATION_PATH = pack_derivation_path(ADA_SHELLEY_DERIVATION_PATH)


class Errors(IntEnum):
    SW_SWAP_CHECKING_FAIL = 0x6001
    SW_SUCCESS            = 0x9000


class CardanoClient:

    def __init__(self, backend: BackendInterface):
        self._backend = backend


    def _check_signature_validity(self, path: str, signature: bytes, data: bytes) -> None:
        """Check the signature validity

        Args:
            path (str): The derivation path
            signature (bytes): The received signature
            data (bytes): The signed data
        """

        ref_pk, _ = calculate_public_key_and_chaincode(CurveChoice.Ed25519Kholaw, path)
        pk: VerifyingKey = VerifyingKey.from_string(bytes.fromhex(ref_pk[2:]), curve=Ed25519)
        assert pk.verify(signature, data, sha512)


    # def perform_byron_sign_tx(self, path: str, destination: str, send_amount: int, send_fees: int) -> None:
    #     """Send a Sign TX command to the Cardano app.
    #        Based on Byron, address type THIRD_PARTY

    #     Args:
    #         path (str): Derivation path
    #         destination (str): Destination address
    #         send_amount (int): Amount to send
    #         send_fees (int): Fees to pay

    #     Returns:
    #         Tuple[bytes, bytes]: Data Hash and the Signature
    #     """

    #     dest_len = len(destination) // 2
    #     output_len = 2 + 4 + dest_len + len(send_amount) // 2 + 6
    #     signTx = {
    #         # Based on ragger testsByron: Sign tx with third-party Byron mainnet output
    #         "signTxInit": "d72101003c0000000000000000012d964a090201010101010101010103000000010000000100000000000000000000000000000000000000000000000000000001",
    #         "signTxInputs": "d7210200241af8fa0b754ff99253d983894e63a2b09cbb56c833ba18c3384210163f63dcfc00000000",
    #         "signTxOutputBasic": f"d7210330{output_len:02x}0001{dest_len:08x}{destination}{send_amount}000000000101",
    #         "signTxOutputConfirm": "d721033300",
    #         "signTxFees": f"d721040008{send_fees}",
    #         "signTxTtl": "d721050008000000000000000a",
    #         "signTxConfirm": "d7210a0000",
    #         "signTxWitness": f"d7210f0015{pack_derivation_path(path).hex()}",
    #     }

    #     data: str = ""
    #     signature: str = ""
    #     for step, value in signTx.items():
    #         response = self._backend.exchange_raw(bytes.fromhex(value))
    #         assert response.status == Errors.SW_SUCCESS
    #         if step == "signTxConfirm":
    #             # Retrieve the data hash
    #             data = response.data
    #         elif step == "signTxWitness":
    #             # Retrieve the signature
    #             signature = response.data

    #     self._check_signature_validity(path, signature, data)


    def perform_shelley_sign_tx(self, destination: str, send_amount: int, send_fees: int) -> None:
        """Send a Sign TX command to the Cardano app.
           Based on Shelley, address type DEVICE_OWNED

        Args:
            destination (str): Destination address
            send_amount (int): Amount to send
            send_fees (int): Fees to pay

        Returns:
            Tuple[bytes, bytes]: Data Hash and the Signature
        """

        if destination is None:
            raise ValueError(f"Invalid destination address: {destination}")

        witness_path1 = "m/1852'/1815'/2'/1/0"
        witness_path2 = "m/1852'/1815'/2'/2/0"
        dest_len = len(destination) // 2
        output_len = 6 + dest_len + len(send_amount) // 2 + 6
        signTx = {
            # Based on LL example output
            "getVersion": "d700000000",
            "deriveAddress": "d71101002d0001058000073c8000071780000002000000000000000222058000073c80000717800000020000000200000000",
            "signTxInit": "d72101003c0000000000000000012d964a090201010101010101010103000000010000000200000000000000010000000000000000000000000000000000000002",
            "signTxInputs": "d7210200247c50edd7d2b7891dc3c33fade1ea557ac748bf177af7088e622f1454b6f71d0d00000000",
            # Send To address (destination)
            "signTxOutputBasic1": f"d7210330{output_len:02x}0101{dest_len:08x}{destination}{send_amount}000000000101",
            "signTxOutputConfirm1": "d721033300",
            # Send From address
            "signTxOutputBasic2": "d72103303d01020001058000073c8000071780000002000000010000000122058000073c800007178000000200000002000000000000000000476009000000000101",
            "signTxOutputConfirm2": "d721033300",
            "signTxFees": f"d721040008{send_fees}",
            "signTxTtl": "d72105000800000000085f492b",
            "SignTxWithdrawals": "d72107001e0000000000004f1b00058000073c80000717800000020000000200000000",
            "signTxConfirm": "d7210a0000",
            "signTxWitness1": f"d7210f0015{pack_derivation_path(witness_path1).hex()}",
            "signTxWitness2": f"d7210f0015{pack_derivation_path(witness_path2).hex()}",
        }

        data = bytes()
        for step, value in signTx.items():
            response = self._backend.exchange_raw(bytes.fromhex(value))
            assert response.status == Errors.SW_SUCCESS
            if step == "signTxConfirm":
                # Retrieve the data hash
                data = response.data
            elif step.startswith("signTxWitness"):
                # Retrieve the signature
                signature = response.data
                # Verify the signature for the selected path
                witness_path = witness_path1 if step == "signTxWitness1" else witness_path2
                self._check_signature_validity(witness_path, signature, data)

