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
        self.last_error: str = ""

    def _collect_unpacked_files(self, archive: Path, out_path: Path) -> list:
        """
        REE.Unpacker'ın dosya çıkarabileceği olası tüm dizinleri (out_path, tools/ altı,
        PAK dosyasının yanındaki *_unpack klasörleri) tarar ve tüm çıkarılan dosyaları out_path klasörüne taşır.
        """
        out_path.mkdir(parents=True, exist_ok=True)
        search_dirs = []

        # 1. PAK dosyasının yanındaki *_unpack veya arşiv isimli klasörler
        if archive.parent.exists():
            for p in archive.parent.glob("*_unpack"):
                if p.is_dir() and p.resolve() != out_path.resolve():
                    search_dirs.append(p)
            pak_stem_dir = archive.parent / archive.stem
            if pak_stem_dir.is_dir() and pak_stem_dir.resolve() != out_path.resolve() and pak_stem_dir not in search_dirs:
                search_dirs.append(pak_stem_dir)

        # 2. tools/ altındaki *_unpack klasörleri veya doğrudan çıkarılan alt dizinler (natives, stm vb.)
        if self.tools_dir.exists():
            for p in self.tools_dir.glob("*_unpack"):
                if p.is_dir() and p.resolve() != out_path.resolve() and p not in search_dirs:
                    search_dirs.append(p)
            tools_stem_dir = self.tools_dir / archive.stem
            if tools_stem_dir.is_dir() and tools_stem_dir.resolve() != out_path.resolve() and tools_stem_dir not in search_dirs:
                search_dirs.append(tools_stem_dir)
            
            # RE Engine oyun arşivlerinin yaygın kök dizinleri (tools/ içine çıktıysa)
            for sub_name in ["natives", "stm"]:
                sub_dir = self.tools_dir / sub_name
                if sub_dir.is_dir() and sub_dir.resolve() != out_path.resolve() and sub_dir not in search_dirs:
                    search_dirs.append(sub_dir)

        # Bulunan tüm dizinlerdeki dosyaları hiyerarşiyi koruyarak out_path içine taşı
        for src_dir in search_dirs:
            logger.info(f"Çıkarılan dosyalar tespit edildi ({src_dir}), hedef klasöre taşınıyor -> {out_path}")
            for item in src_dir.rglob("*"):
                if item.is_file():
                    rel_p = item.relative_to(src_dir)
                    dest_file = out_path / rel_p
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, dest_file)
            # Taşıma sonrası geçici klasörü temizle
            try:
                shutil.rmtree(src_dir, ignore_errors=True)
            except Exception as e:
                logger.warning(f"Geçici klasör silinemedi ({src_dir}): {e}")

        # out_path içindeki tüm geçerli dosyaları listele
        return [f for f in out_path.rglob("*") if f.is_file()]

    def extract_archive(self, archive_path: str, output_dir: str, list_file: Optional[str] = "OWOTS_STM_Release") -> bool:
        """
        `tools/REE.Unpacker.exe` kullanarak RE Engine .pak arşivini belirtilen klasöre çıkarır.
        Argüman sırası: [unpacker_path, archive_path, list_file]
        Çalışma dizini (cwd): tools_dir
        """
        self.last_error = ""
        archive = Path(archive_path).resolve()
        out_path = Path(output_dir).resolve()

        if not archive.exists():
            self.last_error = f"Arşiv dosyası bulunamadı: {archive}"
            logger.error(self.last_error)
            return False

        if not self.unpacker_exe.exists():
            self.last_error = f"REE.Unpacker.exe aracı bulunamadı: {self.unpacker_exe}"
            logger.error(self.last_error)
            return False

        list_tag = list_file or "OWOTS_STM_Release"
        if list_tag.endswith(".list"):
            list_tag = list_tag[:-5]

        out_path.mkdir(parents=True, exist_ok=True)

        # İstenen argüman sırası: [unpacker_path, archive_path, list_file]
        cmd = [
            str(self.unpacker_exe),
            str(archive),
            list_tag
        ]

        logger.info(f"PAK Arşivi Açılıyor: {' '.join(cmd)}")
        logger.info(f"Çalışma Dizini (CWD): {self.tools_dir}")
        try:
            result = subprocess.run(
                cmd, 
                cwd=str(self.tools_dir),
                capture_output=True, 
                text=True
            )

            # Çıktıları anlık gui konsoluna yazdır
            if result.stdout:
                for line in result.stdout.strip().splitlines():
                    if line.strip():
                        logger.info(f"[REE.Unpacker] {line}")
            if result.stderr:
                for line in result.stderr.strip().splitlines():
                    if line.strip():
                        logger.warning(f"[REE.Unpacker ERR] {line}")

            # Çıkarılan dosyaları tara ve hedef klasöre taşı
            extracted_files = self._collect_unpacked_files(archive, out_path)

            # Eğer hiç dosya bulunamadıysa ve araç sözdizimi uyarısı verdiyse,
            # [unpacker_path, list_file, archive_path, output_dir] kombinasyonunu otomatik dene:
            if not extracted_files:
                alt_cmd = [
                    str(self.unpacker_exe),
                    list_tag,
                    str(archive),
                    str(out_path)
                ]
                logger.info(f"İlk çağrıda dosya bulunamadı, alternatif parametre sırası deneniyor: {' '.join(alt_cmd)}")
                alt_result = subprocess.run(
                    alt_cmd,
                    cwd=str(self.tools_dir),
                    capture_output=True,
                    text=True
                )
                if alt_result.stdout:
                    for line in alt_result.stdout.strip().splitlines():
                        if line.strip():
                            logger.info(f"[REE.Unpacker] {line}")
                if alt_result.stderr:
                    for line in alt_result.stderr.strip().splitlines():
                        if line.strip():
                            logger.warning(f"[REE.Unpacker ERR] {line}")

                extracted_files = self._collect_unpacked_files(archive, out_path)

            if not extracted_files:
                combined_out = (result.stdout + "\n" + (alt_result.stdout if 'alt_result' in locals() else '')).strip()
                combined_err = (result.stderr + "\n" + (alt_result.stderr if 'alt_result' in locals() else '')).strip()
                self.last_error = (
                    f"PAK arşivi açıldı fakat hiçbir dosya elde edilemedi!\n\n"
                    f"Taranan yerler: {out_path}, {self.tools_dir} ve {archive.parent}/*_unpack\n"
                    f"Çıktı Özeti:\n{combined_out or combined_err or 'Çıktı yok'}"
                )
                logger.error(self.last_error)
                return False

            logger.info(f"PAK Açma Başarılı. Toplam {len(extracted_files)} dosya '{out_path}' klasörüne toplandı.")
            return True

        except Exception as e:
            self.last_error = f"PAK arşivi açılırken beklenmeyen hata: {e}"
            logger.error(self.last_error)
            return False

    def export_to_json(self, input_dir: str, json_out_dir: str) -> bool:
        """
        `input_dir` içindeki `.msg` dosyalarını REMSG Converter ile JSON formatına aktarır.
        """
        self.last_error = ""
        in_path = Path(input_dir).resolve()
        out_path = Path(json_out_dir).resolve()

        if not in_path.exists():
            self.last_error = f"Dışarı aktarılacak metin klasörü bulunamadı: {in_path}"
            logger.error(self.last_error)
            return False

        if not self.remsg_converter_main.exists():
            self.last_error = f"REMSG_Converter scripti bulunamadı: {self.remsg_converter_main}"
            logger.error(self.last_error)
            return False

        # Giriş klasöründe .msg dosyası var mı?
        all_msg_files = list(in_path.rglob("*.msg*"))
        if not all_msg_files:
            self.last_error = f"Klasörde ({in_path}) dönüştürülecek hiçbir .msg dosyası bulunamadı!\nUnpacker çıktısını veya dosya yapısını kontrol edin."
            logger.error(self.last_error)
            return False

        out_path.mkdir(parents=True, exist_ok=True)

        cmd = [
            sys.executable,
            str(self.remsg_converter_main),
            "-i", str(in_path),
            "-m", "json"
        ]

        logger.info(f"MSG -> JSON Dönüştürme Başlatılıyor: {' '.join(cmd)}")
        try:
            env = os.environ.copy()
            src_dir = str(self.remsg_converter_main.parent)
            env["PYTHONPATH"] = src_dir + os.pathsep + env.get("PYTHONPATH", "")

            result = subprocess.run(cmd, capture_output=True, text=True, env=env)

            # Çıktıları anlık konsola yazdır
            if result.stdout:
                for line in result.stdout.strip().splitlines():
                    if line.strip():
                        logger.info(f"[REMSG_Converter] {line}")
            if result.stderr:
                for line in result.stderr.strip().splitlines():
                    if line.strip():
                        logger.warning(f"[REMSG_Converter ERR] {line}")

            if result.returncode != 0:
                err_details = (result.stderr or result.stdout or f"Hata Kodu: {result.returncode}").strip()
                self.last_error = f"REMSG_Converter (MSG -> JSON) başarısız oldu (Returncode {result.returncode}):\n{err_details}"
                logger.error(self.last_error)
                return False

            # Oluşturulan .msg.json dosyalarını target json_out_dir klasörüne taşı/kopyala
            msg_json_files = list(in_path.rglob("*.msg.json"))
            if not msg_json_files:
                err_details = (result.stderr or result.stdout or "REMSG_Converter çıktı üretmedi.").strip()
                self.last_error = f"REMSG_Converter çalıştı ancak hiçbir .msg.json dosyası oluşturulamadı!\nDetay: {err_details}"
                logger.error(self.last_error)
                return False

            logger.info(f"Dönüştürülen JSON Dosyası Sayısı: {len(msg_json_files)}")
            for json_file in msg_json_files:
                rel_path = json_file.relative_to(in_path)
                dest_file = out_path / rel_path
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(json_file, dest_file)

            return True
        except Exception as e:
            self.last_error = f"MSG -> JSON dönüştürme sırasında hata: {e}"
            logger.error(self.last_error)
            return False

    def import_from_json(self, json_dir: str, output_dir: str, original_msg_dir: Optional[str] = None) -> bool:
        """
        Çevrilmiş JSON dosyalarını orijinal `.msg` yapısı ile birleştirip derlenmiş `.msg` dosyaları üretir.
        """
        self.last_error = ""
        j_path = Path(json_dir).resolve()
        out_path = Path(output_dir).resolve()
        orig_msg_path = Path(original_msg_dir).resolve() if original_msg_dir else j_path

        if not j_path.exists():
            self.last_error = f"JSON klasörü bulunamadı: {j_path}"
            logger.error(self.last_error)
            return False

        json_files = list(j_path.rglob("*.json"))
        if not json_files:
            self.last_error = f"Derlenecek hiçbir JSON dosyası bulunamadı: {j_path}"
            logger.error(self.last_error)
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

            result = subprocess.run(cmd, capture_output=True, text=True, env=env)

            # Çıktıları anlık konsola yazdır
            if result.stdout:
                for line in result.stdout.strip().splitlines():
                    if line.strip():
                        logger.info(f"[REMSG_Converter] {line}")
            if result.stderr:
                for line in result.stderr.strip().splitlines():
                    if line.strip():
                        logger.warning(f"[REMSG_Converter ERR] {line}")

            if result.returncode != 0:
                err_details = (result.stderr or result.stdout or f"Hata Kodu: {result.returncode}").strip()
                self.last_error = f"REMSG_Converter (JSON -> MSG) başarısız oldu (Returncode {result.returncode}):\n{err_details}"
                logger.error(self.last_error)
                return False

            # Oluşturulan .msg.new veya yeni .msg dosyalarını output_dir klasörüne kopyala
            new_msg_files = list(orig_msg_path.rglob("*.msg.new")) + [
                f for f in orig_msg_path.rglob("*.msg") if f.is_file()
            ]
            if not new_msg_files:
                err_details = (result.stderr or result.stdout or "Yeni MSG dosyaları bulunamadı.").strip()
                self.last_error = f"JSON -> MSG derlemesi tamamlandı ancak derlenmiş dosya üretilemedi!\nDetay: {err_details}"
                logger.error(self.last_error)
                return False

            logger.info(f"Derlenen MSG Dosyası Sayısı: {len(new_msg_files)}")
            for msg_file in new_msg_files:
                target_name = msg_file.name[:-4] if msg_file.name.endswith(".new") else msg_file.name
                rel_path = msg_file.relative_to(orig_msg_path).parent / target_name
                dest_file = out_path / rel_path
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(msg_file, dest_file)

            return True
        except Exception as e:
            self.last_error = f"JSON -> MSG derleme sırasında hata: {e}"
            logger.error(self.last_error)
            return False

    def build_mod_package(self, translated_dir: str, mod_output_dir: str, mod_name: str = "Turkish_Translation_Mod") -> bool:
        """
        Derlenmiş metin dosyalarını Fluffy Mod Manager / RE Engine mod klasör yapısına göre paketler.
        """
        self.last_error = ""
        trans_path = Path(translated_dir).resolve()
        mod_out_path = Path(mod_output_dir).resolve() / mod_name

        if not trans_path.exists():
            self.last_error = f"Mod paketlenecek çeviri klasörü bulunamadı: {trans_path}"
            logger.error(self.last_error)
            return False

        files = [f for f in trans_path.rglob("*") if f.is_file()]
        if not files:
            self.last_error = f"Paketlenecek derlenmiş mod dosyası bulunamadı ({trans_path} boş)!"
            logger.error(self.last_error)
            return False

        try:
            mod_out_path.mkdir(parents=True, exist_ok=True)
            shutil.copytree(trans_path, mod_out_path, dirs_exist_ok=True)

            zip_path = Path(mod_output_dir) / f"{mod_name}.zip"
            shutil.make_archive(str(mod_out_path), 'zip', str(mod_out_path))

            logger.info(f"Mod Paketi Başarıyla Oluşturuldu: {mod_out_path} ve {zip_path}")
            return True
        except Exception as e:
            self.last_error = f"Mod paketi oluşturulurken hata: {e}"
            logger.error(self.last_error)
            return False
