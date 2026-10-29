"""Real cryptographic fixtures for the code-signature verifier; no live policy changes."""
import hashlib
import importlib.util
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('code_verifier', ROOT/'tools/verify-darling-code-signature.py')
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def fixture(signer=None, entitlements=None):
    # Fixed reservation means LC_CODE_SIGNATURE is sealed before CMS creation.
    prefix = struct.pack('<8I', 0xfeedfacf, 0x1000007, 3, 2, 1, 16, 0, 0)
    prefix += struct.pack('<4I', 0x1d, 16, 4096, 16384)
    prefix = prefix.ljust(4096, b'\0')
    identity = b'fixture.identifier\0'
    team = b'FIXTURE-TEAM\0'
    special = 5 if entitlements else 0
    hash_offset = 52 + len(identity) + len(team) + special * 32
    directory = struct.pack('>9I4BI2I', 0xfade0c02, hash_offset + 32, 0x20200,
                            0 if signer else 2, hash_offset, 52, special, 1, 4096,
                            32, 2, 0, 12, 0, 0, 52 + len(identity))
    directory += identity + team
    if special:
        directory += hashlib.sha256(entitlements).digest() + bytes(4 * 32)
    directory += hashlib.sha256(prefix).digest()
    blobs = [(0, directory)]
    if entitlements: blobs.append((5, entitlements))
    if signer:
        cms = signer(directory)
        blobs.append((0x10000, struct.pack('>2I', 0xfade0b01, len(cms)+8) + cms))
    length = 12 + len(blobs)*8 + sum(len(blob) for slot, blob in blobs)
    signature = struct.pack('>3I', 0xfade0cc0, length, len(blobs))
    offset = 12 + len(blobs)*8
    for slot, blob in blobs:
        signature += struct.pack('>2I', slot, offset)
        offset += len(blob)
    signature += b''.join(blob for slot, blob in blobs)
    assert len(signature) <= 16384
    return prefix + signature.ljust(16384, b'\0')


class SignatureChecks(unittest.TestCase):
    def test_adhoc_integrity_is_not_trusted_signing(self):
        result = verifier.verify(fixture())
        self.assertTrue(result['integrity_verified'])
        self.assertTrue(result['ad_hoc'])
        self.assertFalse(result['cms_verified'])
        self.assertFalse(result['anchor_verified'])
        self.assertEqual(result['identifier'], 'fixture.identifier')
        self.assertEqual(result['declared_team_id'], 'FIXTURE-TEAM')

    def test_tampered_code_and_unhashed_tail_fail(self):
        image = fixture()
        for bad in [image[:100]+b'X'+image[101:], image+b'X', image[:-1], image[:4096]+b'X'+image[4097:]]:
            with self.assertRaises(ValueError): verifier.verify(bad)

    def test_entitlements_must_be_sealed_and_untampered(self):
        entitlements = struct.pack('>2I', 0xfade7171, 16) + b'contents'
        image = fixture(entitlements=entitlements)
        self.assertTrue(verifier.verify(image)['integrity_verified'])
        position = image.index(b'contents')
        with self.assertRaises(ValueError): verifier.verify(image[:position]+b'X'+image[position+1:])

    def test_signature_slots_cannot_overlap_or_repeat(self):
        image = bytearray(fixture(entitlements=struct.pack('>2I',0xfade7171,8)))
        struct.pack_into('>I', image, 4096+20, 0)  # duplicate primary slot
        with self.assertRaises(ValueError): verifier.verify(bytes(image))
        image = bytearray(fixture(entitlements=struct.pack('>2I',0xfade7171,8)))
        struct.pack_into('>I', image, 4096+24, 28)  # overlapping CodeDirectory
        with self.assertRaises(ValueError): verifier.verify(bytes(image))

    def test_local_trust_is_exact_image_pin_not_universal_membership(self):
        image = fixture()
        cache = {'schema': 1, 'image_sha256': [hashlib.sha256(image).hexdigest()]}
        self.assertTrue(verifier.verify(image, trust_cache=cache)['local_trust_match'])
        self.assertFalse(verifier.verify(image, trust_cache={'schema':1,'image_sha256':[]})['local_trust_match'])
        self.assertFalse(verifier.verify(image, trust_cache=cache)['anchor_verified'])
        with self.assertRaises(ValueError): verifier.verify(image, trust_cache={'schema':True,'image_sha256':[]})

    @unittest.skipUnless(shutil.which('clang') and shutil.which('ld64.lld'), 'Darwin cross-linker required')
    def test_real_linker_produced_adhoc_signature(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'main.s').write_text('.globl _main\n_main:\n xorl %eax,%eax\n retq\n')
            subprocess.run(['clang','-target','x86_64-apple-macosx11','-c',str(root/'main.s'),'-o',str(root/'main.o')],check=True,capture_output=True)
            subprocess.run(['ld64.lld','-arch','x86_64','-platform_version','macos','11.0','11.0',
                            '-adhoc_codesign',str(root/'main.o'),'-o',str(root/'signed')],check=True,capture_output=True)
            image = (root/'signed').read_bytes()
            self.assertTrue(verifier.verify(image)['integrity_verified'])
            image = bytearray(image); image[1000] ^= 1
            with self.assertRaises(ValueError): verifier.verify(bytes(image))

    def test_malformed_input_is_rejected(self):
        for data in [b'', bytes(32), b'\xca\xfe\xba\xbe'+bytes(100), fixture()[:50]]:
            with self.assertRaises(ValueError): verifier.verify(data)


@unittest.skipUnless(shutil.which('openssl'), 'OpenSSL required')
class CMSSignatureChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        def run(*args):
            subprocess.run(['openssl', *args], cwd=cls.root, check=True, capture_output=True, timeout=30)
        cls.run_openssl = staticmethod(run)
        run('req','-x509','-newkey','rsa:2048','-nodes','-keyout','ca.key','-out','ca.pem',
            '-subj','/CN=Disposable Code Test CA','-days','1')
        run('req','-newkey','rsa:2048','-nodes','-keyout','signer.key','-out','signer.csr',
            '-subj','/CN=Disposable Code Signer')
        (cls.root/'extensions').write_text('basicConstraints=critical,CA:FALSE\nkeyUsage=digitalSignature\nextendedKeyUsage=codeSigning\n')
        run('x509','-req','-in','signer.csr','-CA','ca.pem','-CAkey','ca.key','-CAcreateserial',
            '-out','signer.pem','-days','1','-extfile','extensions')
        run('req','-x509','-newkey','rsa:2048','-nodes','-keyout','other.key','-out','other.pem',
            '-subj','/CN=Unrelated CA','-days','1')

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def sign(self, directory):
        (self.root/'directory').write_bytes(directory)
        self.run_openssl('cms','-sign','-binary','-in','directory','-signer','signer.pem','-inkey','signer.key',
                         '-outform','DER','-out','cms','-md','sha256')
        return (self.root/'cms').read_bytes()

    def test_real_cms_signature_and_explicit_chain(self):
        image = fixture(self.sign)
        unanchored = verifier.verify(image)
        self.assertTrue(unanchored['cms_verified'])
        self.assertFalse(unanchored['anchor_verified'])
        anchored = verifier.verify(image, self.root/'ca.pem')
        self.assertTrue(anchored['anchor_verified'])
        self.assertIn('Disposable Code Signer', anchored['signer'])
        with self.assertRaises(ValueError): verifier.verify(image, self.root/'other.pem')

    def test_signed_identifier_tamper_is_detected_by_cms(self):
        image = fixture(self.sign)
        offset = image.index(b'fixture.identifier')
        changed = image[:offset] + b'X' + image[offset+1:]
        with self.assertRaises(ValueError): verifier.verify(changed, self.root/'ca.pem')

    def test_cms_bit_flip_rejected(self):
        image = fixture(self.sign)
        offset, blobs = verifier.signature_blobs(image)
        cms = blobs[0x10000]
        start = image.index(cms)
        changed = bytearray(image); changed[start+len(cms)-1] ^= 1
        with self.assertRaises(ValueError): verifier.verify(bytes(changed), self.root/'ca.pem')
