"""
security_utils.py – TLS-Zertifikat-Verwaltung & API-Key-Verschlüsselung
Gemeinsam genutzt von Server- und Client-Scripten.

Benötigt: pip install cryptography
"""

import os
import sys
import socket
import hashlib
import base64
import datetime
import subprocess
from pathlib import Path

def get_base_dir() -> str:
    """Gibt das Basisverzeichnis zurück – funktioniert als .py und als .exe (PyInstaller)."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

CERT_DIR = Path(get_base_dir()) / "certs"
CA_KEY_FILE   = CERT_DIR / "ca.key"
CA_CERT_FILE  = CERT_DIR / "ca.crt"
SRV_KEY_FILE  = CERT_DIR / "server.key"
SRV_CERT_FILE = CERT_DIR / "server.crt"
SRV_IP_FILE   = CERT_DIR / "server.ip"   # Gespeicherte IP des letzten Zertifikats


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def get_local_ip() -> str:
    """Ermittelt die primäre lokale IP-Adresse (nicht 127.0.0.1)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


# ---------------------------------------------------------------------------
# Zertifikat-Generierung
# ---------------------------------------------------------------------------

def _now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def _generate_ca():
    """Erstellt ein neues CA-Schlüsselpaar und selbstsigniertes Root-Zertifikat."""
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Asklaion Local CA"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Asklaion"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_now_utc())
        .not_valid_after(_now_utc() + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    CA_KEY_FILE.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    CA_CERT_FILE.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print(f"[TLS] Neue CA erstellt: {CA_CERT_FILE}")
    return key, cert


def _load_ca():
    """Lädt das vorhandene CA-Schlüsselpaar von der Festplatte."""
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    from cryptography import x509

    key  = load_pem_private_key(CA_KEY_FILE.read_bytes(), password=None)
    cert = x509.load_pem_x509_certificate(CA_CERT_FILE.read_bytes())
    return key, cert


def _generate_server_cert(ca_key, ca_cert, ip: str):
    """Erstellt ein Server-Zertifikat, signiert durch die CA, gültig für die angegebene IP."""
    import ipaddress
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, f"Asklaion Server {ip}"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_now_utc())
        .not_valid_after(_now_utc() + datetime.timedelta(days=825))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.IPAddress(ipaddress.IPv4Address(ip)),
                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                x509.DNSName("localhost"),
            ]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    SRV_KEY_FILE.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    SRV_CERT_FILE.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    SRV_IP_FILE.write_text(ip, encoding="utf-8")
    print(f"[TLS] Server-Zertifikat erstellt für IP: {ip}")


# ---------------------------------------------------------------------------
# Haupt-Einstiegspunkt (Server)
# ---------------------------------------------------------------------------

def ensure_tls_certs() -> tuple:
    """
    Stellt sicher, dass CA- und Server-Zertifikat existieren und zur aktuellen
    IP passen. Wird beim Server-Start aufgerufen.

    Rückgabe: (cert_file, key_file, ca_cert_file, current_ip)
    """
    CERT_DIR.mkdir(exist_ok=True)
    current_ip = get_local_ip()

    # CA erzeugen falls nicht vorhanden
    if not CA_KEY_FILE.exists() or not CA_CERT_FILE.exists():
        _generate_ca()

    ca_key, ca_cert = _load_ca()

    # Server-Zertifikat prüfen / neu erzeugen
    needs_regen = (
        not SRV_CERT_FILE.exists()
        or not SRV_KEY_FILE.exists()
        or not SRV_IP_FILE.exists()
        or SRV_IP_FILE.read_text(encoding="utf-8").strip() != current_ip
    )

    if needs_regen:
        if SRV_IP_FILE.exists():
            old = SRV_IP_FILE.read_text(encoding="utf-8").strip()
            if old != current_ip:
                print(f"[TLS] IP geändert ({old} → {current_ip}), erneuere Zertifikat...")
        _generate_server_cert(ca_key, ca_cert, current_ip)

    return str(SRV_CERT_FILE), str(SRV_KEY_FILE), str(CA_CERT_FILE), current_ip


# ---------------------------------------------------------------------------
# API-Key-Verschlüsselung (Client)
# ---------------------------------------------------------------------------

def _get_machine_key() -> bytes:
    """
    Leitet einen Fernet-Schlüssel aus der Windows-Maschinen-GUID ab.
    Damit ist config.json maschinenspezifisch verschlüsselt.
    """
    guid = "asklaion-fallback-2024"
    try:
        import winreg
        hk = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
        guid, _ = winreg.QueryValueEx(hk, "MachineGuid")
        winreg.CloseKey(hk)
    except Exception:
        pass
    raw = hashlib.sha256(guid.encode()).digest()
    return base64.urlsafe_b64encode(raw)


_ENC_PREFIX = "enc:"


def encrypt_value(plaintext: str) -> str:
    """Verschlüsselt einen Klartext-String. Gibt 'enc:<token>' zurück."""
    from cryptography.fernet import Fernet
    return _ENC_PREFIX + Fernet(_get_machine_key()).encrypt(plaintext.encode()).decode()


def decrypt_value(value: str) -> str:
    """
    Entschlüsselt einen mit encrypt_value() verschlüsselten Wert.
    Gibt den Klartext zurück. Ist der Wert kein 'enc:'-String, wird er
    unverändert zurückgegeben (Migrations-Fallback).
    """
    if not is_encrypted(value):
        return value
    from cryptography.fernet import Fernet
    return Fernet(_get_machine_key()).decrypt(value[len(_ENC_PREFIX):].encode()).decode()


def is_encrypted(value: str) -> bool:
    """Gibt True zurück wenn der Wert mit encrypt_value() verschlüsselt wurde."""
    return isinstance(value, str) and value.startswith(_ENC_PREFIX)


# ---------------------------------------------------------------------------
# Windows-Systemvertrauen (optional, für Browser-Zugriff)
# ---------------------------------------------------------------------------

def open_ca_for_system_install(ca_cert_path: str):
    """
    Öffnet das CA-Zertifikat mit dem Windows-Zertifikat-Importassistenten.
    Der Nutzer klickt sich durch den Assistenten (kein UAC-Code nötig).
    Sinnvoll wenn der Server auch per Browser erreichbar sein soll.
    """
    os.startfile(ca_cert_path)
