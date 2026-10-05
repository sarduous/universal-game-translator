from abc import ABC, abstractmethod
from typing import Optional


class BaseEngineAdapter(ABC):
    """
    Farklı oyun motorları (RE Engine, Unreal, Unity vb.) için 
    ortak adaptör arayüzü (Abstract Base Class).
    """

    @abstractmethod
    def extract_archive(self, archive_path: str, output_dir: str, list_file: Optional[str] = None) -> bool:
        """
        Oyun arşiv paketinden (.pak, .pak.patch vb.) dosyaları dışarı çıkarır.
        
        Args:
            archive_path: Açılacak paket dosyasının yolu.
            output_dir: Çıkarılan dosyaların yerleştirileceği klasör.
            list_file: İsteğe bağlı proje/liste adı veya dosyası.
        """
        pass

    @abstractmethod
    def export_to_json(self, input_dir: str, json_out_dir: str) -> bool:
        """
        Ham oyun metin dosyalarını (.msg, .locres, .assets vb.) işlenebilir JSON formatına çevirir.
        
        Args:
            input_dir: Dışarı çıkarılmış ham metin dosyalarının bulunduğu klasör.
            json_out_dir: Oluşturulacak JSON dosyalarının kaydedileceği klasör.
        """
        pass

    @abstractmethod
    def import_from_json(self, json_dir: str, output_dir: str) -> bool:
        """
        Çevrilmiş ve düzenlenmiş JSON dosyalarını tekrar oyunun okuyacağı ikili (binary) formata dönüştürür.
        
        Args:
            json_dir: Çevrilmiş JSON dosyalarının klasörü.
            output_dir: Derlenmiş oyun dosyalarının (.msg vb.) kaydedileceği klasör.
        """
        pass

    @abstractmethod
    def build_mod_package(self, translated_dir: str, mod_output_dir: str) -> bool:
        """
        Çevrilen ve derlenen metin dosyalarından oyunun tanıyacağı mod hiyerarşisini veya paketini üretir.
        
        Args:
            translated_dir: Derlenmiş mod dosyalarının klasörü.
            mod_output_dir: Mod paketinin (veya ZIP/PAK dosyasının) hedef klasörü.
        """
        pass
