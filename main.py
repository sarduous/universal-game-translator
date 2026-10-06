import os
import sys
import json
import logging
import argparse
from pathlib import Path
from typing import Any, Dict, List, Tuple

from core.sanitizer import mask_tags, unmask_tags
from core.cache import TranslationCache
from core.translator import GeminiTranslator
from adapters.re_engine import REEngineAdapter
from adapters.base import BaseEngineAdapter

# Logging yapılandırması
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("MainOrchestrator")


ADAPTER_MAP = {
    "re_engine": REEngineAdapter
}


def get_adapter(engine_type: str) -> BaseEngineAdapter:
    adapter_cls = ADAPTER_MAP.get(engine_type.lower())
    if not adapter_cls:
        raise ValueError(f"Desteklenmeyen motor tipi: {engine_type}. Desteklenenler: {list(ADAPTER_MAP.keys())}")
    return adapter_cls()


def translate_json_content(
    json_data: Any, 
    translator: GeminiTranslator, 
    cache: TranslationCache, 
    batch_size: int = 25
) -> Any:
    """
    JSON yapısı içindeki metinleri tespit eder, etiketlerini maskeler, 
    önbelleği sorgular ve çevrilmeyenleri LLM paket çevirisine tabi tutarak geri yerleştirir.
    """
    extracted_strings: List[str] = []
    string_locations: List[Tuple[Any, Any]] = []  # (obj, key_or_index)

    def collect_strings(node: Any, parent: Any = None, key: Any = None):
        if isinstance(node, str):
            if node.strip():
                extracted_strings.append(node)
                string_locations.append((parent, key))
        elif isinstance(node, dict):
            for k, v in node.items():
                collect_strings(v, node, k)
        elif isinstance(node, list):
            for idx, item in enumerate(node):
                collect_strings(item, node, idx)

    collect_strings(json_data)

    if not extracted_strings:
        return json_data

    logger.info(f"JSON içinden toplam {len(extracted_strings)} adet metin çıkarıldı.")

    # 1. Maskeleme
    masked_items = []
    for s in extracted_strings:
        masked_text, tag_map = mask_tags(s)
        masked_items.append({
            "original": s,
            "masked": masked_text,
            "tag_map": tag_map
        })

    # 2. Önbellek Sorgulama
    to_translate_masked = []
    to_translate_indices = []
    cache_hits = 0

    for idx, item in enumerate(masked_items):
        cached = cache.get(item["masked"])
        if cached is not None:
            item["translated_masked"] = cached
            cache_hits += 1
        else:
            to_translate_masked.append(item["masked"])
            to_translate_indices.append(idx)

    if cache_hits > 0:
        hit_msg = f"[INFO] [CACHE HIT] {cache_hits} satır önbellekten okundu (0 token)"
        print(hit_msg)
        logger.info(hit_msg)
    else:
        logger.info(f"Önbellek İsabeti: {cache_hits} | Çevrilecek Yeni Metin: {len(to_translate_masked)}")

    # 3. LLM Çevirisi (Batch)
    if to_translate_masked:
        logger.info(f"LLM API'ye {len(to_translate_masked)} metin paketler halinde gönderiliyor...")
        translations = translator.translate_batch(to_translate_masked, batch_size=batch_size)
        
        for idx, trans_text in zip(to_translate_indices, translations):
            masked_items[idx]["translated_masked"] = trans_text
            cache.set(masked_items[idx]["masked"], trans_text)

    # 4. Etiketleri Geri Yükleme ve JSON Yapısını Güncelleme
    for idx, (parent, key) in enumerate(string_locations):
        item = masked_items[idx]
        final_tr = unmask_tags(item["translated_masked"], item["tag_map"])
        parent[key] = final_tr

    return json_data


def process_json_directory(
    json_in_dir: Path, 
    json_out_dir: Path, 
    translator: GeminiTranslator, 
    cache_db_path: str = None,
    batch_size: int = 25
):
    """
    Export edilen tüm JSON dosyalarını tarar ve çevirerek hedef klasöre kaydeder.
    """
    json_files = list(json_in_dir.rglob("*.json"))
    logger.info(f"İşlenecek Toplam JSON Dosyası Sayısı: {len(json_files)}")

    with TranslationCache(cache_db_path) as cache:
        for json_file in json_files:
            rel_path = json_file.relative_to(json_in_dir)
            out_file = json_out_dir / rel_path

            # Dosya seviyesinde resume: Zaten diskte varsa ve içi doluysa atla
            if out_file.exists() and out_file.stat().st_size > 0:
                skip_msg = f"[INFO] {json_file.name} zaten çevrilmiş, atlanıyor."
                print(skip_msg)
                logger.info(skip_msg)
                continue

            logger.info(f"Çevriliyor: {json_file.name}")
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                translated_data = translate_json_content(data, translator, cache, batch_size=batch_size)

                out_file.parent.mkdir(parents=True, exist_ok=True)
                with open(out_file, "w", encoding="utf-8") as f:
                    json.dump(translated_data, f, ensure_ascii=False, indent=2)

            except Exception as e:
                logger.error(f"JSON çeviri hatası ({json_file.name}): {e}")

    logger.info("Tüm JSON dosyalarının çevirisi tamamlandı.")


def main():
    parser = argparse.ArgumentParser(
        prog="Universal Game Translator CLI",
        description="Oyun arşivlerini açan, metinlerini çıkaran, LLM ile çeviren ve mod olarak derleyen orkestratör."
    )

    parser.add_argument("--archive", "-a", type=str, help="Çevrilecek oyun PAK arşiv dosyası yolu")
    parser.add_argument("--output-dir", "-o", type=str, default="output", help="Çalışma ve mod çıktı klasörü (varsayılan: output)")
    parser.add_argument("--engine", "-e", type=str, default="re_engine", choices=["re_engine"], help="Oyun motoru adaptörü")
    parser.add_argument("--list-file", "-l", type=str, default="OWOTS_STM_Release", help="Unpacker için proje/liste etiketi")
    parser.add_argument("--batch-size", "-b", type=int, default=25, help="LLM çeviri paket boyutu (varsayılan: 25)")
    parser.add_argument("--cache-db", type=str, default="translation_cache.db", help="Önbellek veritabanı dosyası")
    parser.add_argument("--api-key", type=str, help="Gemini API Anahtarı")
    parser.add_argument("--skip-extract", action="store_true", help="Arşiv çıkarma adımını atla")
    parser.add_argument("--skip-translate", action="store_true", help="LLM Çeviri adımını atla")

    args = parser.parse_args()

    base_out = Path(args.output_dir).resolve()
    unpacked_dir = base_out / "unpacked"
    exported_json_dir = base_out / "json_raw"
    translated_json_dir = base_out / "json_translated"
    compiled_msg_dir = base_out / "msg_compiled"
    mod_output_dir = base_out / "mod_package"

    adapter = get_adapter(args.engine)
    translator = GeminiTranslator(api_key=args.api_key)

    logger.info("=== UNIVERSAL GAME TRANSLATOR ORKESTRATÖRÜ BAŞLATILDI ===")

    # ADIM 1: Arşivi Çıkar (Extract)
    if not args.skip_extract:
        if not args.archive:
            logger.error("--skip-extract kullanılmadıysa --archive parametresi gereklidir!")
            sys.exit(1)
        logger.info("--- ADIM 1: Oyun Arşivi Çıkarılıyor ---")
        success = adapter.extract_archive(args.archive, str(unpacked_dir), list_file=args.list_file)
        if not success:
            logger.error("Arşiv çıkarma başarısız oldu!")
            sys.exit(1)
    else:
        logger.info("--- ADIM 1: Arşiv çıkarma adımı atlandı. ---")

    # ADIM 2: JSON'a Aktar (Export to JSON)
    logger.info("--- ADIM 2: Ham Metinler JSON Formatına Dönüştürülüyor ---")
    if unpacked_dir.exists():
        success = adapter.export_to_json(str(unpacked_dir), str(exported_json_dir))
        if not success:
            logger.error(f"Adım 2/5 (MSG -> JSON Aktarma) başarısız oldu:\n{getattr(adapter, 'last_error', '')}")
            sys.exit(1)
    else:
        logger.error(f"Adım 2/5 Başarısız: Unpacked klasörü bulunamadı: {unpacked_dir}")
        sys.exit(1)

    # ADIM 3: Çekirdek Çeviri Motoru (Core Translation)
    if not args.skip_translate:
        logger.info("--- ADIM 3: Çekirdek Çeviri Motoru Çalıştırılıyor (Mask + Cache + Batch LLM) ---")
        json_files = list(exported_json_dir.rglob("*.json")) if exported_json_dir.exists() else []
        if json_files:
            process_json_directory(
                exported_json_dir, 
                translated_json_dir, 
                translator, 
                args.cache_db,
                batch_size=args.batch_size
            )
        else:
            logger.error(f"Adım 3/5 Başarısız: Çevrilecek JSON dosyası bulunamadı ({exported_json_dir})!")
            sys.exit(1)
    else:
        logger.info("--- ADIM 3: Çeviri adımı atlandı. ---")

    # ADIM 4: Tekrar Oyuna Derle (Import to Binary / MSG)
    logger.info("--- ADIM 4: Çevrilmiş JSON'lar İkili Formata (MSG) Derleniyor ---")
    source_json_dir = translated_json_dir if translated_json_dir.exists() else exported_json_dir
    if source_json_dir.exists():
        success = adapter.import_from_json(str(source_json_dir), str(compiled_msg_dir), original_msg_dir=str(unpacked_dir) if unpacked_dir.exists() else None)
        if not success:
            logger.error(f"Adım 4/5 (JSON -> MSG Derleme) başarısız oldu:\n{getattr(adapter, 'last_error', '')}")
            sys.exit(1)
    else:
        logger.error(f"Adım 4/5 Başarısız: Derlenecek JSON kaynak klasörü bulunamadı: {source_json_dir}")
        sys.exit(1)

    # ADIM 5: Mod Paketini Hazırla (Build Mod Package)
    logger.info("--- ADIM 5: Mod Paketi Yapılandırılıyor ---")
    if compiled_msg_dir.exists():
        success = adapter.build_mod_package(str(compiled_msg_dir), str(mod_output_dir))
        if not success:
            logger.error(f"Adım 5/5 (Mod Paketleme) başarısız oldu:\n{getattr(adapter, 'last_error', '')}")
            sys.exit(1)
    else:
        logger.error(f"Adım 5/5 Başarısız: Derlenmiş mesaj klasörü bulunamadı: {compiled_msg_dir}")
        sys.exit(1)

    logger.info("=== BÜTÜN İŞLEMLER BAŞARIYLA TAMAMLANDI ===")


if __name__ == "__main__":
    main()
