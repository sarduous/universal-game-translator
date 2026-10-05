import json
import os
import sys
from pathlib import Path

# Project root'u path'e ekle
sys.path.insert(0, str(Path(__file__).parent))

from core.sanitizer import mask_tags, unmask_tags
from core.cache import TranslationCache
from core.translator import GeminiTranslator


def test_sanitizer():
    print("\n--- 1. MODÜL TESTİ: Tag Sanitizer (Format Koruma) ---")
    sample_text = "Warning: <COLOR ff0000>{PlayerName}</COLOR> has %d HP left!\nPress %s to dodge."
    print(f"Orijinal Metin:  {repr(sample_text)}")

    masked, tag_map = mask_tags(sample_text)
    print(f"Maskelenmiş:     {repr(masked)}")
    print(f"Etiket Haritası: {tag_map}")

    restored = unmask_tags(masked, tag_map)
    print(f"Geri Yüklenen:   {repr(restored)}")

    assert restored == sample_text, "HATA: Tag Sanitizer metni orijinal haline getiremedi!"
    print("SUCCESS: Tag Sanitizer (maskeleme / unmasking) başarıyla geçti!\n")


def test_cache():
    print("--- 2. MODÜL TESTİ: Translation Cache (Önbellekleme) ---")
    cache_db = "test_cache.db"
    if os.path.exists(cache_db):
        os.remove(cache_db)

    with TranslationCache(cache_db) as cache:
        test_src = "Honor is true strength."
        test_tr = "Onur, gerçek güçtür."

        # Başlangıçta önbellek boş olmalı
        assert cache.get(test_src) is None, "HATA: Önbellek boş olmalıydı!"

        # Kaydet ve tekrar sorgula
        cache.set(test_src, test_tr)
        cached_val = cache.get(test_src)
        assert cached_val == test_tr, f"HATA: Önbellekten yanlış değer döndü! ({cached_val})"

        print(f"Önbelleğe yazıldı: '{test_src}' -> '{test_tr}'")
        print(f"Önbellekten okundu: '{test_src}' -> '{cached_val}'")
        print(f"Toplam Önbellek Kayıt Sayısı: {cache.count()}")

    if os.path.exists(cache_db):
        os.remove(cache_db)
    print("SUCCESS: Translation Cache (SQLite SHA-256) başarıyla geçti!\n")


def test_full_pipeline():
    print("--- 3. ENTEGRASYON TESTİ: Tam Çeviri Boru Hattı (Full Pipeline) ---")
    mock_file = Path("tests/mock_dialogues.json")
    if not mock_file.exists():
        print(f"HATA: {mock_file} bulunamadı!")
        return

    with open(mock_file, "r", encoding="utf-8") as f:
        dialogues = json.load(f)

    print(f"Yüklenen Sahte Diyalog Sayısı: {len(dialogues)}")

    cache_db = "pipeline_cache.db"
    if os.path.exists(cache_db):
        os.remove(cache_db)

    translator = GeminiTranslator()
    
    def run_pipeline_pass(pass_number: int):
        print(f"\n>>> PAS {pass_number} BAŞLATIYOR... <<<")
        cache_hits = 0
        cache_misses = 0
        final_results = []

        with TranslationCache(cache_db) as cache:
            # Step 1: Etiketleri Maskele
            masked_items = []
            for orig_text in dialogues:
                masked_text, tag_map = mask_tags(orig_text)
                masked_items.append({
                    "original": orig_text,
                    "masked": masked_text,
                    "tag_map": tag_map
                })

            # Step 2: Önbellek Kontrolü
            to_translate = []
            to_translate_indices = []

            for idx, item in enumerate(masked_items):
                cached = cache.get(item["masked"])
                if cached:
                    item["translated_masked"] = cached
                    cache_hits += 1
                else:
                    cache_misses += 1
                    to_translate.append(item["masked"])
                    to_translate_indices.append(idx)

            print(f"Önbellek İsabeti (Cache Hit) : {cache_hits}")
            print(f"Çevrilecek Yeni Metin (Miss): {cache_misses}")

            # Step 3: Çevrilmeyenleri Paket (Batch) Halinde API / Motor Üzerinden Çevir
            if to_translate:
                print(f"API/Translator'a Gönderilen Paket Boyutu: {len(to_translate)}")
                translations = translator.translate_batch(to_translate, batch_size=20)
                
                # Çevirileri Önbelleğe Kaydet ve Öğelere Ata
                for idx, trans_text in zip(to_translate_indices, translations):
                    masked_items[idx]["translated_masked"] = trans_text
                    cache.set(masked_items[idx]["masked"], trans_text)

            # Step 4: Etiketleri Geri Yükle (Unmask)
            for item in masked_items:
                final_tr = unmask_tags(item["translated_masked"], item["tag_map"])
                final_results.append(final_tr)

        # Sonuçları Göster
        print(f"\n--- PAS {pass_number} ÇEVİRİ SONUÇLARI ÖRNEKLERİ ---")
        for i in range(min(5, len(dialogues))):
            print(f"[{i+1}] ORİJİNAL : {dialogues[i]}")
            print(f"    ÇEVİRİ   : {final_results[i]}\n")

        return cache_hits, cache_misses, final_results

    # 1. Pas (İlk kez çeviri, cache doldurma)
    hits_1, misses_1, res_1 = run_pipeline_pass(1)

    # 2. Pas (Aynı metinleri tekrar çevirme -> %100 Cache Hit beklenir)
    hits_2, misses_2, res_2 = run_pipeline_pass(2)

    assert misses_2 == 0, f"HATA: 2. pas aşamasında önbellekten okunmalıydı ama {misses_2} metin kaçırıldı!"
    assert hits_2 == len(dialogues), "HATA: 2. pas tüm metinleri önbellekten getirmeliydi!"

    print("SUCCESS: 2. Pas %100 Cache Hit oranıyla doğrulandı! Sıfır API çağrısı yapıldı.")

    if os.path.exists(cache_db):
        os.remove(cache_db)

    print("\n=======================================================")
    print("  TÜM ÇEKİRDEK ÇEVİRİ MOTORU TESTLERİ BAŞARIYLA GEÇTİ! ")
    print("=======================================================\n")


if __name__ == "__main__":
    test_sanitizer()
    test_cache()
    test_full_pipeline()
