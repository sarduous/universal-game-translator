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
    
    # 1. Varsayılan kalıcı konum testi: data/translations.db
    with TranslationCache() as default_cache:
        assert default_cache.db_path.name == "translations.db", "HATA: Veritabanı adı translations.db olmalı!"
        assert default_cache.db_path.parent.name == "data", "HATA: Veritabanı 'data' klasöründe olmalı!"
        assert default_cache.db_path.parent.exists(), "HATA: data/ klasörü oluşturulmamış!"
        print(f"Varsayılan Kalıcı Önbellek Yolu Doğrulandı: {default_cache.db_path}")

    # 2. Anlık commit ve bağlantı kapatıp tekrar açma testi
    cache_db = "test_cache.db"
    if os.path.exists(cache_db):
        os.remove(cache_db)

    test_src = "Honor is true strength."
    test_tr = "Onur, gerçek güçtür."

    # İlk bağlantı: yaz ve kapat (commit testi)
    with TranslationCache(cache_db) as cache:
        assert cache.get(test_src) is None, "HATA: Önbellek boş olmalıydı!"
        cache.set(test_src, test_tr)
        print(f"Önbelleğe yazıldı: '{test_src}' -> '{test_tr}'")

    # İkinci bağlantı: yeni nesne aç, veri diskte kalıcı mı kontrol et
    with TranslationCache(cache_db) as cache_reopen:
        cached_val = cache_reopen.get(test_src)
        assert cached_val == test_tr, f"HATA: Yeniden açılan bağlantıda veri bulunamadı! ({cached_val})"
        print(f"Yeniden başlatılan oturumda okundu: '{test_src}' -> '{cached_val}'")
        
        # get_batch ve log testi
        batch_res = cache_reopen.get_batch([test_src, "Bilinmeyen Metin"])
        assert test_src in batch_res, "HATA: get_batch beklenen anahtarı içermiyor!"
        print(f"Toplam Önbellek Kayıt Sayısı: {cache_reopen.count()}")

    if os.path.exists(cache_db):
        os.remove(cache_db)
    print("SUCCESS: Translation Cache (Kalıcı SQLite & Anlık Commit) başarıyla geçti!\n")


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
                translations = translator.translate_batch(to_translate, batch_size=25)
                
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


def test_file_resume():
    print("--- 4. ENTEGRASYON TESTİ: File-Level Resume (Zaten Çevrilmiş Dosyayı Atlama) ---")
    import shutil
    from main import process_json_directory

    test_raw_dir = Path("tests/temp_raw")
    test_tr_dir = Path("tests/temp_translated")
    test_raw_dir.mkdir(parents=True, exist_ok=True)
    test_tr_dir.mkdir(parents=True, exist_ok=True)

    dummy_raw_file = test_raw_dir / "sample.json"
    with open(dummy_raw_file, "w", encoding="utf-8") as f:
        json.dump({"dialogue": "Original Text To Translate"}, f)

    # Hedef dosya dolu olarak önceden oluşturuluyor
    dummy_tr_file = test_tr_dir / "sample.json"
    with open(dummy_tr_file, "w", encoding="utf-8") as f:
        json.dump({"dialogue": "Önceden Çevrilmiş Metin"}, f)

    translator = GeminiTranslator()
    cache_path = "tests/test_resume_cache.db"

    # process_json_directory çağrıldığında dosya atlanmalı ve üzerine yazılmamalı
    process_json_directory(test_raw_dir, test_tr_dir, translator, cache_db_path=cache_path)

    # İçeriğin bozulmadığını kontrol et
    with open(dummy_tr_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["dialogue"] == "Önceden Çevrilmiş Metin", "HATA: Zaten var olan dosya atlanmadı veya üzerine yazıldı!"
    print(f"SUCCESS: {dummy_raw_file.name} başarıyla tespit edildi ve atlandı!")

    # Temizlik
    if test_raw_dir.exists():
        shutil.rmtree(test_raw_dir)
    if test_tr_dir.exists():
        shutil.rmtree(test_tr_dir)
    if os.path.exists(cache_path):
        os.remove(cache_path)


if __name__ == "__main__":
    test_sanitizer()
    test_cache()
    test_full_pipeline()
    test_file_resume()
    print("\n=======================================================")
    print("  TÜM ÇEKİRDEK ÇEVİRİ MOTORU VE RESUME TESTLERİ GEÇTİ!  ")
    print("=======================================================\n")

