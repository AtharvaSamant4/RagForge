"""Versioned streaming AES-256-GCM backups; authenticate before using plaintext."""
import os
from pathlib import Path
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC=b'RAGFORGE-BACKUP-1\x00'


def derive(passphrase,salt):
    if len(passphrase)<20:raise ValueError('Backup passphrase must contain at least 20 characters')
    return Scrypt(salt=salt,length=32,n=2**15,r=8,p=1).derive(passphrase.encode())


def encrypt(source:Path,target:Path,passphrase:str):
    salt=os.urandom(16);nonce=os.urandom(12);header=MAGIC+salt+nonce
    cipher=Cipher(algorithms.AES(derive(passphrase,salt)),modes.GCM(nonce)).encryptor()
    cipher.authenticate_additional_data(header)
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,'wb') as out,source.open('rb') as inp:
            out.write(header)
            while block:=inp.read(1024*1024):out.write(cipher.update(block))
            out.write(cipher.finalize());out.write(cipher.tag)
    except Exception:
        target.unlink(missing_ok=True);raise


def decrypt(source:Path,target:Path,passphrase:str,max_bytes=2*1024**3):
    if source.stat().st_size>max_bytes or source.stat().st_size<len(MAGIC)+44:raise ValueError('Invalid or oversized backup')
    with source.open('rb') as inp:
        header=inp.read(len(MAGIC)+28)
        if not header.startswith(MAGIC):raise ValueError('Unsupported backup version')
        salt=header[len(MAGIC):len(MAGIC)+16];nonce=header[-12:]
        inp.seek(-16,2);tag=inp.read(16);inp.seek(len(header))
        remaining=source.stat().st_size-len(header)-16
        cipher=Cipher(algorithms.AES(derive(passphrase,salt)),modes.GCM(nonce,tag)).decryptor()
        cipher.authenticate_additional_data(header)
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        try:
            with os.fdopen(fd,'wb') as out:
                while remaining:
                    block=inp.read(min(1024*1024,remaining));remaining-=len(block)
                    if not block:raise ValueError('Truncated backup')
                    out.write(cipher.update(block))
                out.write(cipher.finalize())
        except Exception:
            target.unlink(missing_ok=True)
            raise ValueError('Backup authentication failed; no restore was performed') from None
