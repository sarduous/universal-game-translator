import os
import sys
import shutil
import subprocess
import logging
from pathlib import Path
from typing import Optional

from adapters.base import BaseEngineAdapter

logger = logging.getLogger(__name__)


class REEngineAdapter(BaseEngineAdapter):
    """
    Capcom RE Engine oyunları (.pak, .msg) için özel adaptör sınıfı.
    `tools/REE.Unpacker.exe` ve `tools/REMSG_Converter` araçlarını kullanır.
    """

    def __init__(self, tools_dir: Optional[str] = None):
        self.project_root = Path(__file__).resolve().parent.parent
        self.tools_dir = Path(tools_dir) if tools_dir else self.project_root / "tools"
        self.unpacker_exe = self.tools_dir / "REE.Unpacker.exe"
        self.remsg_converter_main = self.tools_dir / "REMSG_Converter" / "src" / "main.py"

    def extract_archive(self, archive_path: str, output_dir: str, list_file: Optional[str] = "OWOTS_STM_Release") -> bool:
        """
        `tools/REE.Unpacker.exe` kullanarak RE Engine .pak arşivini belirtilen klasöre çıkarır.
        """
        archive = Path(archive_path).resolve()
        out_path = Path(output_dir).resolve()

        if not archive.exists():
            logger.error(f"Arşiv dosyası bulunamadı: {archive}")
            return False

        if not self.unpacker_exe.exists():
            logger.error(f"REE.Unpacker.exe bulunamadı: {self.unpacker_exe}")
            return False

        list_tag = list_file or "OWOTS_STM_Release"
        out_path.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(self.unpacker_exe),
            list_tag,
            str(archive),
            str(out_path)
        ]

        logger.info(f"PAK Arşivi Açılıyor: {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info("PAK Açma Başarılı.")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"PAK Açma Hatası: {e.stderr or e.stdout or e}")
            return False

    def export_to_json(self, input_dir: str, json_out_dir: str) -> bool:
        """
        `input_dir` içindeki `.msg` dosyalarını REMSG Converter ile JSON formatına aktarır.
        """
        in_path = Path(input_dir).resolve()
        out_path = Path(json_out_dir).resolve()

        if not in_path.exists():
            logger.error(f"Dışarı aktarılacak metin klasörü bulunamadı: {in_path}")
            return False

        out_path.mkdir(parents=True, exist_ok=True)

        if not self.remsg_converter_main.exists():
            logger.error(f"REMSG_Converter scripti bulunamadı: {self.remsg_converter_main}")
            return False

        cmd = [
            sys.executable,
            str(self.remsg_converter_main),
            "-i", str(in_path),
            "-m", "json"
        ]

        logger.info(f"MSG -> JSON Dönüştürme Başlatılıyor: {' '.join(cmd)}")
        try:
            env = os.environ.copy()
            # REMSG_Converter src dizinini PYTHONPATH'e ekle
            src_dir = str(self.remsg_converter_main.parent)
            env["PYTHONPATH"] = src_dir + os.pathsep + env.get("PYTHONPATH", "")

            result = subprocess.run(cmd, capture_output=True, text=True, env=env, check=True)
            
            # Oluşturulan .msg.json dosyalarını target json_out_dir klasörüne taşı/kopyala
            msg_json_files = list(in_path.rglob("*.msg.json"))
            logger.info(f"Dönüştürülen JSON Dosyası Sayısı: {len(msg_json_files)}")

            for json_file in msg_json_files:
                rel_path = json_file.relative_to(in_path)
                dest_file = out_path / rel_path
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(json_file, dest_file)

            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"MSG -> JSON Dönüştürme Hatası: {e.stderr or e.stdout or e}")
            return False

    def import_from_json(self, json_dir: str, output_dir: str, original_msg_dir: Optional[str] = None) -> bool:
        """
        Çevrilmiş JSON dosyalarını orijinal `.msg` yapısı ile birleştirip derlenmiş `.msg` dosyaları üretir.
        """
        j_path = Path(json_dir).resolve()
        out_path = Path(output_dir).resolve()
        orig_msg_path = Path(original_msg_dir).resolve() if original_msg_dir else j_path

        if not j_path.exists():
            logger.error(f"JSON klasörü bulunamadı: {j_path}")
            return False

        out_path.mkdir(parents=True, exist_ok=True)

        cmd = [
            sys.executable,
            str(self.remsg_converter_main),
            "-i", str(orig_msg_path),
            "-e", str(j_path),
            "-m", "json"
        ]

        logger.info(f"JSON -> MSG Derleme Başlatılıyor: {' '.join(cmd)}")
        try:
            env = os.environ.copy()
            src_dir = str(self.remsg_converter_main.parent)
            env["PYTHONPATH"] = src_dir + os.pathsep + env.get("PYTHONPATH", "")

            result = subprocess.run(cmd, capture_output=True, text=True, env=env, check=True)
            
            # Oluşturulan .msg.new veya yeni .msg dosyalarını output_dir klasörüne kopyala
            new_msg_files = list(orig_msg_path.rglob("*.msg.new")) + list(orig_msg_path.rglob("*.msg"))
            logger.info(f"Derlenen MSG Dosyası Sayısı: {len(new_msg_files)}")

            for msg_file in new_msg_files:
                target_name = msg_file.name[:-4] if msg_file.name.endswith(".new") else msg_file.name
                rel_path = msg_file.relative_to(orig_msg_path).parent / target_name
                dest_file = out_path / rel_path
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(msg_file, dest_file)

            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"JSON -> MSG Derleme Hatası: {e.stderr or e.stdout or e}")
            return False

    def build_mod_package(self, translated_dir: str, mod_output_dir: str, mod_name: str = "Turkish_Translation_Mod") -> bool:
        """
        Derlenmiş metin dosyalarını Fluffy Mod Manager / RE Engine mod klasör yapısına göre paketler.
        """
        trans_path = Path(translated_dir).resolve()
        mod_out_path = Path(mod_output_dir).resolve() / mod_name

        if not trans_path.exists():
            logger.error(f"Mod paketlenecek çeviri klasörü bulunamadı: {trans_path}")
            return False

        mod_out_path.mkdir(parents=True, exist_ok=True)

        # RE Engine mod yapısı genelde natives/STM/... veya doğrudan dosya ağacını takip eder
        shutil.copytree(trans_path, mod_out_path, dirs_exist_ok=True)

        # zip paketi de oluştur
        zip_path = Path(mod_output_dir) / f"{mod_name}.zip"
        shutil.make_archive(str(mod_out_path), 'zip', str(mod_out_path))

        logger.info(f"Mod Paketi Başarıyla Oluşturuldu: {mod_out_path} ve {zip_path}")
        return True
