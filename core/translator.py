import os
import re
import json
import time
import logging
from typing import List, Optional
from pathlib import Path
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

logger = logging.getLogger(__name__)

INVALID_KEY_PLACEHOLDERS = {
    "",
    "your_key_here",
    "BURAYA_API_KEY_GELECEK",
    "YOUR_GEMINI_API_KEY",
    "AIzaSyYourKeyHere"
}


def is_valid_gemini_key(key: Optional[str]) -> bool:
    """
    Verilen Gemini API anahtarının geçerli bir yapıda olup olmadığını kontrol eder.
    Yer tutucu (placeholder) veya boş değerleri geçersiz kabul eder.
    """
    if not key or not isinstance(key, str):
        return False
    key = key.strip()
    if key in INVALID_KEY_PLACEHOLDERS:
        return False
    if len(key) < 15 or " " in key or "\n" in key:
        return False
    return True


SYSTEM_PROMPT = """Sen feodal Japonya / Samuray temalı epik bir aksiyon video oyununun kıdemli Türkçe yerelleştirme uzmanısın.
Görevin, sana verilen İngilizce oyun diyaloglarını ve arayüz metinlerini Türkçeye çevirmektir.

ÇEVİRİ KURALLARI VE TALİMATLAR:
1. TON VE ÜSLUP: Samuray atmosferine uygun, ciddi, vakur, racon içeren ve aksiyon hissini yansıtan doğal bir Türkçe kullan.
2. ETİKET KORUMASI: Metinlerde geçen __TAG_0__, __TAG_1__, __TAG_2__ gibi tüm maskeleme etiketlerini KESİNLİKLE orijinal yerlerinde ve aynen koru. Değiştirme, silme veya çevirme!
3. FORMAT: Cevabını KESİNLİKLE sadece geçerli bir JSON string listesi (Array of strings) formatında ver.
   Örnek Girdi: ["Draw your sword, __TAG_0__!", "Defeat the enemies."]
   Örnek Çıktı: ["Kılıcını çek, __TAG_0__!", "Düşmanları bozguna uğrat."]
4. Girdi dizisindeki eleman sayısı ile çıktı dizisindeki eleman sayısı BİREBİR AYNI olmalıdır.
5. Markdown kod blokları veya ekstra açıklama yazma. Sadece ham JSON array döndür."""


MODEL_FALLBACK_CHAIN = [
    "gemini-3.1-flash-lite",   # 500 RPD, 15 RPM (Ana model)
    "gemini-3.5-flash-lite"    # 500 RPD, 15 RPM (Yedek)
]


class GeminiTranslator:
    """
    Google GenAI SDK kullanarak diyalogları paketler (batch) halinde Türkçeye çeviren LLM motoru.
    Kademeli Model Fallback Listesi (Fallback Chain) ile kota ve hata yönetimini otomatik yapar.
    """

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        # En güncel .env değerini belleğe al
        load_dotenv(dotenv_path=ENV_PATH, override=True)
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")

        # Fallback zincirini başlat
        self.model_chain = list(MODEL_FALLBACK_CHAIN)

        # Eğer kullanıcı özel bir model belirttiyse zincirdeki konumunu belirle
        requested_model = model_name or os.getenv("GEMINI_MODEL")
        if requested_model and requested_model in self.model_chain:
            self.current_model_idx = self.model_chain.index(requested_model)
        elif requested_model:
            # Özel belirtilen model zincirin başına eklenir
            self.model_chain.insert(0, requested_model)
            self.current_model_idx = 0
        else:
            self.current_model_idx = 0

        self.client = None

        if is_valid_gemini_key(self.api_key):
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
                logger.info(f"Google GenAI Client başarıyla başlatıldı (Aktif Model: {self.current_model}).")
            except Exception as e:
                logger.warning(f"Google GenAI Client başlatılamadı: {e}")
        else:
            logger.info("Geçerli bir GEMINI_API_KEY bulunamadı veya varsayılan değerde. Çevirici Mock (simülasyon) modunda çalışacak.")

    @property
    def current_model(self) -> str:
        if 0 <= self.current_model_idx < len(self.model_chain):
            return self.model_chain[self.current_model_idx]
        return self.model_chain[-1]

    @property
    def model_name(self) -> str:
        return self.current_model

    @model_name.setter
    def model_name(self, value: str):
        if value in self.model_chain:
            self.current_model_idx = self.model_chain.index(value)
        else:
            self.model_chain.insert(0, value)
            self.current_model_idx = 0

    def _switch_to_next_model(self) -> Optional[str]:
        """
        Kota aşımı (429) durumunda fallback zincirindeki sonraki modele geçer.
        """
        if self.current_model_idx + 1 < len(self.model_chain):
            old_model = self.current_model
            self.current_model_idx += 1
            new_model = self.current_model
            msg = f"[WARN] {old_model} kotası/isteği aşıldı, sıradaki modele geçiliyor: {new_model}"
            print(msg)
            logger.warning(msg)
            return new_model
        return None

    def translate_batch(
        self, 
        texts: List[str], 
        batch_size: int = 25, 
        max_retries: int = 3, 
        retry_delay: float = 2.0
    ) -> List[str]:
        """
        Metin listesini belirtilen batch boyutunda (varsayılan 25) parçalara bölerek çevirir.
        Her yeni batch'e başlarken her zaman listenin 1. modeli olan gemini-3.1-flash-lite ile başlar.
        15 RPM sınırını aşmamak için her batch çağrısı arasına 4.1 saniye güvenli bekleme süresi koyar.
        """
        if not texts:
            return []

        all_translations = []
        total_chunks = (len(texts) + batch_size - 1) // batch_size

        for chunk_idx, i in enumerate(range(0, len(texts), batch_size), 1):
            # Model Sıfırlama: Her yeni batch'e başlarken her zaman listenin 1. modeli olan gemini-3.1-flash-lite ile başla
            self.current_model_idx = 0

            chunk = texts[i:i + batch_size]
            translated_chunk = self._translate_chunk_with_retry(
                chunk, 
                max_retries=max_retries, 
                retry_delay=retry_delay
            )
            all_translations.extend(translated_chunk)

            # 15 RPM hız sınırını aşmamak için paketler arasına güvenli bekleme koy
            if chunk_idx < total_chunks and self.client is not None:
                logger.info("15 RPM hız limiti koruması: 4.1 saniye güvenli bekleme uygulanıyor...")
                time.sleep(4.1)

        return all_translations

    def _translate_chunk_with_retry(
        self, 
        chunk: List[str], 
        max_retries: int = 3, 
        retry_delay: float = 2.0
    ) -> List[str]:
        r"""
        Tek bir paketi (chunk) çevirir ve rate limit / hata durumlarında:
        - 429 / RESOURCE_EXHAUSTED: sıradaki modele geçer.
        - 503 UNAVAILABLE / bağlantı hatası: model DEĞİŞTİRMEZ, 5 saniye bekleyip aynı modelle tekrar dener (maksimum 3 deneme).
        - JSON ayıklama: re.search(r"\[.*\]", raw_text, re.DOTALL) ile JSON array'i ayıklar.
        """
        if not self.client:
            # API Key yoksa test amaçlı Mock Çeviri üret
            return [self._mock_translate(text) for text in chunk]

        from google.genai import types

        prompt_payload = json.dumps(chunk, ensure_ascii=False)

        while True:
            current_model = self.current_model
            model_switched = False

            for attempt in range(1, max_retries + 1):
                try:
                    response = self.client.models.generate_content(
                        model=current_model,
                        contents=f"Aşağıdaki JSON dizisindeki metinleri Türkçeye çevir:\n{prompt_payload}",
                        config=types.GenerateContentConfig(
                            system_instruction=SYSTEM_PROMPT,
                            temperature=0.3,
                            response_mime_type="application/json"
                        )
                    )

                    raw_text = (response.text or "").strip()
                    
                    # Markdown veya ekstra metinleri ayıkla: re.search ile [ ... ] array bloğunu bul
                    match = re.search(r"\[.*\]", raw_text, re.DOTALL)
                    json_str = match.group(0) if match else raw_text

                    translations = json.loads(json_str)

                    if isinstance(translations, list) and len(translations) == len(chunk):
                        return [str(t) for t in translations]
                    else:
                        logger.warning(
                            f"Çıktı boyutu uyuşmuyor (Beklenen: {len(chunk)}, Gelen: {len(translations) if isinstance(translations, list) else 'Geçersiz'}). Model: {current_model}, Deneme {attempt}/{max_retries}"
                        )
                        if attempt < max_retries:
                            time.sleep(retry_delay * attempt)
                        continue

                except json.JSONDecodeError as e:
                    logger.warning(
                        f"JSON Parse Hatası (Model: {current_model}, Deneme {attempt}/{max_retries}): {e}. Format hatası yüzünden model değiştirilmiyor, tekrar deneniyor."
                    )
                    if attempt < max_retries:
                        time.sleep(retry_delay * attempt)
                    continue

                except Exception as e:
                    err_str = str(e).upper()
                    logger.error(f"Gemini API Hatası (Model: {current_model}, Deneme {attempt}/{max_retries}): {e}")

                    # 1. YALNIZCA 429 / RESOURCE_EXHAUSTED hatası alındığında sıradaki modele geç
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        next_model = self._switch_to_next_model()
                        if next_model:
                            model_switched = True
                            break  # attempt döngüsünden çık, yeni modelle paketi anında tekrar dene
                        else:
                            logger.error("Tüm modellerin kotası doldu (429 RESOURCE_EXHAUSTED).")
                            return chunk

                    # 2. 503 UNAVAILABLE veya bağlantı hatası alındığında model DEĞİŞTİRME; 5 saniye bekle ve aynı modelle tekrar dene (maksimum 3 deneme)
                    elif any(c in err_str for c in ["503", "UNAVAILABLE", "CONNECTION", "TIMEOUT", "DISCONNECTED"]):
                        logger.warning(
                            f"503 UNAVAILABLE veya bağlantı hatası alındı. Model DEĞİŞTİRİLMİYOR, 5 saniye bekleniyor... (Deneme {attempt}/{max_retries})"
                        )
                        if attempt < max_retries:
                            time.sleep(5.0)
                        continue

                    # 3. Diğer genel hatalarda standart bekleme uygula
                    else:
                        if attempt < max_retries:
                            time.sleep(retry_delay * (2 ** (attempt - 1)))
                        continue

            if model_switched:
                # 429 sebebiyle sıradaki modele geçildi; mevcut paket yeni modelle anında tekrar denenir
                continue

            # Denemeler tükendi (503 veya genel hata). Format veya 503 için model değiştirilmez.
            logger.error(f"Paket çevrilemedi ({current_model}). Orijinal metinler korunuyor.")
            return chunk

    def _mock_translate(self, text: str) -> str:
        """
        API Key olmadan test yapabilmek için sahte Samuray temalı çevirici.
        Maskelenmiş etiket kalıplarını koruyarak Türkçe karşılık döndürür.
        """
        mock_dictionary = {
            "Draw your sword, __TAG_0__!": "Kılıcını çek, __TAG_0__!",
            "You cannot defeat the __TAG_0__Shadow Samurai__TAG_1__.": "__TAG_0__Gölge Samuray__TAG_1__'ı asla yenemezsin.",
            "Health restored by __TAG_0__ points.__TAG_1__Prepare for battle!": "Canın __TAG_0__ puan yenilendi.__TAG_1__Savaşa hazırlan!",
            "Press __TAG_0__ to open the inventory.": "Envanteri açmak için __TAG_0__ tuşuna bas.",
            "Defeat 5 dishonorable bandits in the village.": "Köydeki 5 onursuz haydudu bozguna uğrat.",
            "Honor is true strength.": "Onur, gerçek güçtür.",
            "The blade responds to your spirit.": "Kılıç senin ruhunla yankılanıyor.",
            "Guard your posture!": "Duruşunu koru!",
            "Warning: __TAG_0__Poisonous Gas__TAG_1__ ahead!": "Uyarı: İleride __TAG_0__Zehirli Gaz__TAG_1__ var!",
            "Do not turn your back on the enemy.": "Düşmana asla sırtını dönme.",
            "The master said: \"Patience is a weapon.\"": "Usta şöyle dedi: \"Sabır bir silahtır.\"",
            "Victory belongs to the brave.": "Zafer cesurlara aittir."
        }
        
        return mock_dictionary.get(text, f"[TR] {text}")
