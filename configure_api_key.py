#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Universal AI Game Translator - Gemini API Anahtarı Yapılandırma Aracı
Bu betik, terminal üzerinden güvenli bir şekilde Gemini API anahtarınızı alır,
.env dosyasını günceller ve isteğe bağlı olarak Google GenAI bağlantısını test eder.
"""

import os
import sys
import getpass
from pathlib import Path
from dotenv import load_dotenv

# Proje ana dizinini ve modülleri dahil et
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.translator import is_valid_gemini_key, ENV_PATH


def save_api_key(api_key: str) -> None:
    api_key = api_key.strip()
    lines = []
    found = False

    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

    new_lines = []
    for line in lines:
        if line.strip().startswith("GEMINI_API_KEY="):
            new_lines.append(f"GEMINI_API_KEY={api_key}\n")
            found = True
        else:
            new_lines.append(line)

    if not found:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")
        new_lines.append(f"GEMINI_API_KEY={api_key}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    load_dotenv(dotenv_path=ENV_PATH, override=True)


def test_api_connection(api_key: str) -> bool:
    print("\n⏳ Gemini API bağlantısı test ediliyor...")
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        for model in ["gemini-2.5-flash-lite", "gemini-flash-lite-latest", "gemini-1.5-flash"]:
            try:
                response = client.models.generate_content(
                    model=model,
                    contents="Say 'OK' if you can read this."
                )
                if response and response.text:
                    print(f"✅ Bağlantı BAŞARILI! Model: {model} -> {response.text.strip()}")
                    return True
            except Exception:
                continue
        print("⚠️  Uyarı: Modeller test edildi ancak yanıt alınamadı.")
        return False
    except Exception as e:
        print(f"⚠️  Uyarı: Anahtar kaydedildi ancak test çağrısı başarısız oldu: {e}")
        return False


def main():
    print("=" * 60)
    print("  Universal AI Game Translator - Gemini API Key Kurulumu")
    print("=" * 60)

    # Argüman kontrolü
    if len(sys.argv) > 1:
        key = sys.argv[1].strip()
    else:
        print("\nGoogle AI Studio üzerinden aldığınız API anahtarını girin:")
        print("(Girdiğiniz anahtar güvenli şekilde saklanacaktır.)")
        try:
            key = input("Gemini API Key: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nİşlem iptal edildi.")
            return

    if not is_valid_gemini_key(key):
        print("\n❌ HATA: Geçersiz API anahtarı!")
        print("Lütfen boş olmayan ve geçerli bir Gemini API anahtarı girin.")
        return

    # Dosyaya kaydet
    save_api_key(key)
    print(f"\n🎉 Başarılı! .env dosyası güncellendi: {ENV_PATH}")
    print("Durum: 🟢 Gemini API Key Hazır")

    # API testi
    test_api_connection(key)

    print("\nArtık 'python gui.py' komutuyla arayüzü başlatabilirsiniz!")


if __name__ == "__main__":
    main()
