import os
import json
import time
import logging
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

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


class GeminiTranslator:
    """
    Google GenAI SDK kullanarak diyalogları paketler (batch) halinde Türkçeye çeviren LLM motoru.
    """

    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-2.5-flash"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name
        self.client = None

        if self.api_key and self.api_key != "your_key_here":
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Google GenAI Client başlatılamadı: {e}")
        else:
            logger.info("GEMINI_API_KEY bulunamadı veya varsayılan değerde. Çevirici Mock (simülasyon) modunda çalışacak.")

    def translate_batch(
        self, 
        texts: List[str], 
        batch_size: int = 20, 
        max_retries: int = 3, 
        retry_delay: float = 2.0
    ) -> List[str]:
        """
        Metin listesini belirtilen batch boyutunda parçalara bölerek çevirir.
        """
        if not texts:
            return []

        all_translations = []

        for i in range(0, len(texts), batch_size):
            chunk = texts[i:i + batch_size]
            translated_chunk = self._translate_chunk_with_retry(
                chunk, 
                max_retries=max_retries, 
                retry_delay=retry_delay
            )
            all_translations.extend(translated_chunk)

        return all_translations

    def _translate_chunk_with_retry(
        self, 
        chunk: List[str], 
        max_retries: int, 
        retry_delay: float
    ) -> List[str]:
        """
        Tek bir paketi (chunk) çevirir ve rate limit / ağ hatalarına karşı retry/backoff uygular.
        """
        if not self.client:
            # API Key yoksa test amaçlı Mock Çeviri üret
            return [self._mock_translate(text) for text in chunk]

        from google.genai import types

        prompt_payload = json.dumps(chunk, ensure_ascii=False)

        for attempt in range(1, max_retries + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=f"Aşağıdaki JSON dizisindeki metinleri Türkçeye çevir:\n{prompt_payload}",
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        temperature=0.3,
                        response_mime_type="application/json"
                    )
                )

                response_text = response.text.strip()
                
                # Markdown temizleme (eğer model ```json eklediyse)
                if response_text.startswith("```"):
                    response_text = response_text.split("\n", 1)[-1].rsplit("\n", 1)[0].strip()

                translations = json.loads(response_text)

                if isinstance(translations, list) and len(translations) == len(chunk):
                    return [str(t) for t in translations]
                else:
                    logger.warning(
                        f"Çıktı boyutu uyuşmuyor (Beklenen: {len(chunk)}, Gelen: {len(translations) if isinstance(translations, list) else 'Geçersiz'}). Deneme {attempt}/{max_retries}"
                    )

            except Exception as e:
                logger.error(f"Gemini API Hatası (Deneme {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    time.sleep(retry_delay * (2 ** (attempt - 1)))  # Exponential backoff

        logger.error("Maksimum yeniden deneme sayısına ulaşıldı. Orijinal metinler korunuyor.")
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
