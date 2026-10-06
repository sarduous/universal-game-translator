import os
import sys
import json
import queue
import logging
import threading
from pathlib import Path
from typing import Optional

import customtkinter as ctk
from tkinter import filedialog, messagebox
from dotenv import load_dotenv

from core.sanitizer import mask_tags, unmask_tags, safe_font_convert
from core.cache import TranslationCache
from core.translator import GeminiTranslator, is_valid_gemini_key, ENV_PATH
from adapters.re_engine import REEngineAdapter
from adapters.base import BaseEngineAdapter

# .env yükle (Kesin mutlak yol ile)
load_dotenv(dotenv_path=ENV_PATH, override=True)


def save_api_key_to_env(api_key: str) -> bool:
    """
    GEMINI_API_KEY değerini ana dizindeki .env dosyasına güvenle yazar veya günceller.
    Mevcut diğer satırları ve dosya yapısını korur.
    """
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

    os.environ["GEMINI_API_KEY"] = api_key
    load_dotenv(dotenv_path=ENV_PATH, override=True)
    return True

# CustomTkinter varsayılan görünüm (Koyu Tema)
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

# Kırmızı & Siyah Teması Renk Paleti (Samurai Crimson & Obsidian Black)
COLOR_BG = "#0D0D11"          # Ana Pencere Arka Planı (Derin Siyah)
COLOR_CARD = "#14141A"        # Kart/Çerçeve Arka Planı
COLOR_HEADER = "#1A0F12"      # Başlık Alanı Arka Planı
COLOR_TEXT_MAIN = "#F5F5F7"   # Ana Metin (Parlak Beyaz)
COLOR_TEXT_MUTED = "#A0A0B0"  # İkincil Metin (Gri)
COLOR_CRIMSON = "#D32F2F"     # Ana Kırmızı (Crimson Red)
COLOR_CRIMSON_HOVER = "#B71C1C" # Buton Hover Kırmızı
COLOR_ACCENT = "#FF3344"      # Canlı Vurgu Kırmızı
COLOR_INPUT_BG = "#1A1A22"    # Input Kutuları Arka Planı
COLOR_LOG_BG = "#08080A"      # Konsol Siyah Arka Planı
COLOR_LOG_TEXT = "#E0D5D7"    # Konsol Metni


class TextboxLogHandler(logging.Handler):
    """
    Python logging çıktılarını GUI üzerindeki Scrollable Textbox'a canlı olarak yönlendiren Handler.
    """
    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        msg = self.format(record)
        self.log_queue.put(msg + "\n")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Universal AI Game Translator")
        self.geometry("880x760")
        self.minsize(820, 700)
        self.configure(fg_color=COLOR_BG)

        # Uygulama İkonu Ayarla (Kırmızı-Siyah 'S' Logosu)
        icon_path = Path(__file__).parent / "assets" / "app_icon.ico"
        if icon_path.exists():
            try:
                self.iconbitmap(str(icon_path))
            except Exception:
                pass

        self.log_queue = queue.Queue()
        self.pipeline_running = False

        # Grid yapılandırması
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._build_header()
        self._build_engine_section()
        self._build_options_section()
        self._build_progress_and_log_section()
        self._build_action_button()

        # Log kuyruğunu periyodik kontrol et
        self.after(100, self._process_log_queue)

        # Logging yönlendirme
        self._setup_logging()

    def _setup_logging(self):
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.INFO)
        handler = TextboxLogHandler(self.log_queue)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
        self.logger.addHandler(handler)

    def _build_header(self):
        header_frame = ctk.CTkFrame(
            self, 
            corner_radius=12, 
            fg_color=COLOR_HEADER,
            border_width=1,
            border_color="#3D1418"
        )
        header_frame.grid(row=0, column=0, padx=15, pady=(15, 10), sticky="ew")
        header_frame.grid_columnconfigure(1, weight=1)

        # 'S' Logosu Görseli
        png_path = Path(__file__).parent / "assets" / "app_icon.png"
        if png_path.exists():
            try:
                from PIL import Image
                logo_img = ctk.CTkImage(light_image=Image.open(png_path), dark_image=Image.open(png_path), size=(40, 40))
                logo_label = ctk.CTkLabel(header_frame, image=logo_img, text="")
                logo_label.grid(row=0, column=0, rowspan=2, padx=(15, 5), pady=10)
            except Exception:
                pass

        title_label = ctk.CTkLabel(
            header_frame, 
            text="Universal Game Translator", 
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=COLOR_ACCENT
        )
        title_label.grid(row=0, column=1, padx=10, pady=15, sticky="w")

    def _build_engine_section(self):
        engine_frame = ctk.CTkFrame(
            self, 
            corner_radius=12, 
            fg_color=COLOR_CARD,
            border_width=1,
            border_color="#2A1B1F"
        )
        engine_frame.grid(row=1, column=0, padx=15, pady=5, sticky="ew")
        engine_frame.grid_columnconfigure(1, weight=1)

        # Başlık
        sec_title = ctk.CTkLabel(
            engine_frame, 
            text="🎮 Oyun ve Motor Yapılandırması", 
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLOR_ACCENT
        )
        sec_title.grid(row=0, column=0, columnspan=3, padx=15, pady=(10, 5), sticky="w")

        # Motor Seçimi Dropdown
        ctk.CTkLabel(engine_frame, text="Oyun Motoru:", text_color=COLOR_TEXT_MAIN).grid(row=1, column=0, padx=15, pady=5, sticky="w")
        self.engine_dropdown = ctk.CTkOptionMenu(
            engine_frame, 
            values=["RE Engine (Capcom)", "Unreal Engine (Yakında)", "Unity (Yakında)"],
            fg_color="#2B161B",
            button_color=COLOR_CRIMSON,
            button_hover_color=COLOR_CRIMSON_HOVER,
            dropdown_fg_color="#1E1215",
            text_color=COLOR_TEXT_MAIN
        )
        self.engine_dropdown.grid(row=1, column=1, columnspan=2, padx=15, pady=5, sticky="ew")
        self.engine_dropdown.set("RE Engine (Capcom)")

        # PAK Arşiv Seçimi
        ctk.CTkLabel(engine_frame, text="PAK / Arşiv Dosyası:", text_color=COLOR_TEXT_MAIN).grid(row=2, column=0, padx=15, pady=5, sticky="w")
        self.pak_entry = ctk.CTkEntry(
            engine_frame, 
            placeholder_text="Oyun .pak dosya yolunu seçin...",
            fg_color=COLOR_INPUT_BG,
            border_color="#332226",
            text_color=COLOR_TEXT_MAIN
        )
        self.pak_entry.grid(row=2, column=1, padx=(15, 5), pady=5, sticky="ew")
        self.pak_browse_btn = ctk.CTkButton(
            engine_frame, 
            text="Gözat...", 
            width=90, 
            fg_color="#2B181C",
            hover_color="#422026",
            text_color=COLOR_ACCENT,
            border_width=1,
            border_color="#52222B",
            command=self._browse_pak_file
        )
        self.pak_browse_btn.grid(row=2, column=2, padx=(5, 15), pady=5)

        # Proje / Liste Etiketi
        ctk.CTkLabel(engine_frame, text="Proje / Liste Etiketi:", text_color=COLOR_TEXT_MAIN).grid(row=3, column=0, padx=15, pady=5, sticky="w")
        self.list_file_entry = ctk.CTkEntry(
            engine_frame,
            fg_color=COLOR_INPUT_BG,
            border_color="#332226",
            text_color=COLOR_TEXT_MAIN
        )
        self.list_file_entry.insert(0, "OWOTS_STM_Release")
        self.list_file_entry.grid(row=3, column=1, columnspan=2, padx=15, pady=5, sticky="ew")

        # Çıktı Klasörü Seçimi
        ctk.CTkLabel(engine_frame, text="Çıktı Klasörü:", text_color=COLOR_TEXT_MAIN).grid(row=4, column=0, padx=15, pady=5, sticky="w")
        self.out_dir_entry = ctk.CTkEntry(
            engine_frame,
            fg_color=COLOR_INPUT_BG,
            border_color="#332226",
            text_color=COLOR_TEXT_MAIN
        )
        self.out_dir_entry.insert(0, str(Path("./output").resolve()))
        self.out_dir_entry.grid(row=4, column=1, padx=(15, 5), pady=(5, 10), sticky="ew")
        self.out_dir_browse_btn = ctk.CTkButton(
            engine_frame, 
            text="Gözat...", 
            width=90, 
            fg_color="#2B181C",
            hover_color="#422026",
            text_color=COLOR_ACCENT,
            border_width=1,
            border_color="#52222B",
            command=self._browse_output_dir
        )
        self.out_dir_browse_btn.grid(row=4, column=2, padx=(5, 15), pady=(5, 10))

    def _build_options_section(self):
        options_frame = ctk.CTkFrame(
            self, 
            corner_radius=12, 
            fg_color=COLOR_CARD,
            border_width=1,
            border_color="#2A1B1F"
        )
        options_frame.grid(row=2, column=0, padx=15, pady=5, sticky="ew")
        options_frame.grid_columnconfigure(0, weight=1)
        options_frame.grid_columnconfigure(1, weight=0)
        options_frame.grid_columnconfigure(2, weight=0)

        # Font Güvenli Mod Checkbox
        self.font_safe_var = ctk.BooleanVar(value=False)
        self.font_safe_checkbox = ctk.CTkCheckBox(
            options_frame, 
            text="Font Güvenli Mod (Türkçe karakterleri güvenli harflere dönüştür: ç->c, ş->s vb.)",
            variable=self.font_safe_var,
            font=ctk.CTkFont(size=12),
            fg_color=COLOR_CRIMSON,
            hover_color=COLOR_CRIMSON_HOVER,
            checkmark_color="#FFFFFF",
            text_color=COLOR_TEXT_MAIN
        )
        self.font_safe_checkbox.grid(row=0, column=0, padx=15, pady=10, sticky="w")

        # API Durumu Etiketi
        self.api_status_label = ctk.CTkLabel(
            options_frame, 
            text="", 
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.api_status_label.grid(row=0, column=1, padx=(10, 8), pady=10, sticky="e")

        # API Key Tanımla Butonu
        self.api_key_btn = ctk.CTkButton(
            options_frame,
            text="🔑 API Key Gir",
            width=110,
            height=28,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#2B181C",
            hover_color="#422026",
            text_color=COLOR_ACCENT,
            border_width=1,
            border_color="#52222B",
            command=self._prompt_api_key_dialog
        )
        self.api_key_btn.grid(row=0, column=2, padx=(0, 15), pady=10, sticky="e")

        # İlk durum kontrolü
        self._update_api_status()

    def _update_api_status(self):
        """
        .env dosyasını yeniden okuyarak API anahtarının durumunu ve rengini günceller.
        """
        load_dotenv(dotenv_path=ENV_PATH, override=True)
        api_key = os.getenv("GEMINI_API_KEY", "")
        if is_valid_gemini_key(api_key):
            self.api_status_label.configure(
                text="🟢 Gemini API Key Hazır",
                text_color="#50FA7B"
            )
        else:
            self.api_status_label.configure(
                text="🔴 Gemini API Key Bulunamadı (Mock Modu)",
                text_color="#FF5555"
            )

    def _prompt_api_key_dialog(self):
        """
        Kullanıcıdan Gemini API anahtarını güvenli bir iletişim kutusu ile alır ve .env'ye kaydeder.
        """
        dialog = ctk.CTkInputDialog(
            text="Google Gemini API anahtarınızı girin:\n(Örnek: AIzaSy...)",
            title="Gemini API Anahtarı Yapılandırma"
        )
        entered_key = dialog.get_input()
        if entered_key is not None:
            entered_key = entered_key.strip()
            if not is_valid_gemini_key(entered_key):
                messagebox.showerror(
                    "Geçersiz Anahtar",
                    "Girdiğiniz API anahtarı geçersiz veya yer tutucu (placeholder) biçiminde!\nLütfen Google AI Studio'dan aldığınız geçerli anahtarı girin."
                )
                return

            save_api_key_to_env(entered_key)
            self._update_api_status()
            self.logger.info("Gemini API Anahtarı .env dosyasına başarıyla kaydedildi ve arayüze bağlandı.")
            messagebox.showinfo(
                "Başarılı",
                "Gemini API Anahtarınız .env dosyasına kaydedildi!\nDurum: 🟢 Gemini API Key Hazır"
            )


    def _build_progress_and_log_section(self):
        progress_frame = ctk.CTkFrame(
            self, 
            corner_radius=12, 
            fg_color=COLOR_CARD,
            border_width=1,
            border_color="#2A1B1F"
        )
        progress_frame.grid(row=3, column=0, padx=15, pady=5, sticky="nsew")
        progress_frame.grid_columnconfigure(0, weight=1)
        progress_frame.grid_rowconfigure(2, weight=1)

        # Durum Metni
        self.status_label = ctk.CTkLabel(
            progress_frame, 
            text="Hazır - İşlem başlatılmayı bekliyor...", 
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLOR_ACCENT
        )
        self.status_label.grid(row=0, column=0, padx=15, pady=(10, 2), sticky="w")

        # İlerleme Çubuğu (Progress Bar)
        self.progress_bar = ctk.CTkProgressBar(
            progress_frame,
            fg_color="#221418",
            progress_color=COLOR_ACCENT
        )
        self.progress_bar.grid(row=1, column=0, padx=15, pady=(2, 10), sticky="ew")
        self.progress_bar.set(0.0)

        # Canlı Log Kutusu (Scrollable Textbox)
        self.log_textbox = ctk.CTkTextbox(
            progress_frame, 
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=COLOR_LOG_BG,
            text_color=COLOR_LOG_TEXT,
            border_width=1,
            border_color="#26181B"
        )
        self.log_textbox.grid(row=2, column=0, padx=15, pady=(0, 10), sticky="nsew")
        self.log_textbox.insert("1.0", "--- Sistem Konsolu Başlatıldı (Kırmızı/Siyah Samurai Teması) ---\n")
        self.log_textbox.configure(state="disabled")

    def _build_action_button(self):
        self.start_btn = ctk.CTkButton(
            self, 
            text="🚀 Çeviriyi ve Modlamayı Başlat", 
            font=ctk.CTkFont(size=16, weight="bold"),
            height=48,
            fg_color=COLOR_CRIMSON,
            hover_color=COLOR_CRIMSON_HOVER,
            text_color="#FFFFFF",
            corner_radius=10,
            command=self._start_pipeline_thread
        )
        self.start_btn.grid(row=4, column=0, padx=15, pady=15, sticky="ew")

    def _browse_pak_file(self):
        filename = filedialog.askopenfilename(
            title="PAK Arşiv Dosyası Seçin",
            filetypes=[("PAK Arşiv Dosyaları", "*.pak"), ("Tüm Dosyalar", "*.*")]
        )
        if filename:
            self.pak_entry.delete(0, "end")
            self.pak_entry.insert(0, filename)

    def _browse_output_dir(self):
        directory = filedialog.askdirectory(title="Çıktı Klasörünü Seçin")
        if directory:
            self.out_dir_entry.delete(0, "end")
            self.out_dir_entry.insert(0, directory)

    def _process_log_queue(self):
        while not self.log_queue.empty():
            try:
                msg = self.log_queue.get_nowait()
                self.log_textbox.configure(state="normal")
                self.log_textbox.insert("end", msg)
                self.log_textbox.see("end")
                self.log_textbox.configure(state="disabled")
            except queue.Empty:
                break
        self.after(100, self._process_log_queue)

    def _set_status(self, text: str, progress: float):
        self.status_label.configure(text=text)
        self.progress_bar.set(progress)

    def _start_pipeline_thread(self):
        if self.pipeline_running:
            return

        pak_path = self.pak_entry.get().strip()
        if not pak_path or not os.path.exists(pak_path):
            messagebox.showwarning("Eksik Girdi", "Lütfen geçerli bir .pak arşiv dosyası seçin!")
            return

        self.pipeline_running = True
        self.start_btn.configure(state="disabled", text="⏳ İşlem Süyor...")

        thread = threading.Thread(target=self._run_pipeline_worker, args=(pak_path,), daemon=True)
        thread.start()

    def _run_pipeline_worker(self, pak_path: str):
        try:
            out_dir = Path(self.out_dir_entry.get().strip()).resolve()
            list_file = self.list_file_entry.get().strip() or "OWOTS_STM_Release"
            font_safe = self.font_safe_var.get()

            unpacked_dir = out_dir / "unpacked"
            exported_json_dir = out_dir / "json_raw"
            translated_json_dir = out_dir / "json_translated"
            compiled_msg_dir = out_dir / "msg_compiled"
            mod_output_dir = out_dir / "mod_package"

            adapter = REEngineAdapter()
            translator = GeminiTranslator()

            # ADIM 1: PAK Çıkarma (0.15)
            self._set_status("📦 1/5: PAK arşivi açılıyor...", 0.15)
            self.logger.info("--- [ADIM 1/5] PAK Arşivi Açılıyor ---")
            success = adapter.extract_archive(pak_path, str(unpacked_dir), list_file=list_file)
            if not success:
                err_detail = getattr(adapter, 'last_error', '') or "PAK arşivinden dosyalar çıkarılamadı."
                raise RuntimeError(f"[Adım 1/5: PAK Çıkarma Başarısız]\n\n{err_detail}")

            # ADIM 2: JSON'a Aktarma (0.35)
            self._set_status("📄 2/5: Metinler JSON formatına aktarılıyor...", 0.35)
            self.logger.info("--- [ADIM 2/5] Ham Metinler JSON Formatına Aktarılıyor ---")
            success = adapter.export_to_json(str(unpacked_dir), str(exported_json_dir))
            if not success:
                err_detail = getattr(adapter, 'last_error', '') or "Metinler JSON formatına aktarılamadı."
                raise RuntimeError(f"[Adım 2/5: MSG -> JSON Aktarma Başarısız]\n\n{err_detail}")

            # ADIM 3: Çeviri (0.70)
            self._set_status("💬 3/5: Otomatik diyalog çevirisi yapılıyor...", 0.70)
            self.logger.info("--- [ADIM 3/5] Otomatik Diyalog Çevirisi Başlatılıyor ---")
            
            json_files = list(exported_json_dir.rglob("*.json"))
            if not json_files:
                raise RuntimeError(
                    "[Adım 3/5: Çeviri Başarısız]\n\n"
                    f"Çevrilecek hiçbir JSON metin dosyası bulunamadı ({exported_json_dir})!\n"
                    "Lütfen PAK dosyasının metin içerdiğinden ve arşivin doğru açıldığından emin olun."
                )

            with TranslationCache() as cache:
                total_files = len(json_files)
                for idx, json_file in enumerate(json_files, 1):
                    rel_path = json_file.relative_to(exported_json_dir)
                    out_file = translated_json_dir / rel_path

                    # Dosya seviyesinde resume: Çevrilmiş JSON zaten varsa ve içi doluysa atla
                    if out_file.exists() and out_file.stat().st_size > 0:
                        skip_msg = f"[INFO] {json_file.name} zaten çevrilmiş, atlanıyor."
                        print(skip_msg)
                        self.logger.info(skip_msg)
                        continue

                    self.logger.info(f"Metin Dosyası İşleniyor ({idx}/{total_files}): {json_file.name}")
                    try:
                        with open(json_file, "r", encoding="utf-8") as f:
                            data = json.load(f)

                        # Çeviri işlemi
                        translated_data = self._translate_json_data(data, translator, cache, font_safe)

                        out_file.parent.mkdir(parents=True, exist_ok=True)
                        with open(out_file, "w", encoding="utf-8") as f:
                            json.dump(translated_data, f, ensure_ascii=False, indent=2)
                    except Exception as e:
                        raise RuntimeError(f"[Adım 3/5: Çeviri Başarısız]\n\nDosya: {json_file.name}\nHata Detayı: {e}")

            # ADIM 4: MSG Derleme (0.85)
            self._set_status("⚙️ 4/5: Çevrilmiş metinler ikili formata (MSG) derleniyor...", 0.85)
            self.logger.info("--- [ADIM 4/5] JSON -> MSG Derleme Başlatılıyor ---")
            success = adapter.import_from_json(str(translated_json_dir), str(compiled_msg_dir), original_msg_dir=str(unpacked_dir))
            if not success:
                err_detail = getattr(adapter, 'last_error', '') or "Çevrilmiş JSON dosyaları MSG formatına derlenemedi."
                raise RuntimeError(f"[Adım 4/5: JSON -> MSG Derleme Başarısız]\n\n{err_detail}")

            # ADIM 5: Mod Paketi Oluşturma (1.00)
            self._set_status("🎁 5/5: Mod paketi oluşturuluyor...", 1.00)
            self.logger.info("--- [ADIM 5/5] Mod Paketi Yapılandırılıyor ---")
            success = adapter.build_mod_package(str(compiled_msg_dir), str(mod_output_dir))
            if not success:
                err_detail = getattr(adapter, 'last_error', '') or "Mod paketi oluşturulamadı."
                raise RuntimeError(f"[Adım 5/5: Mod Paketleme Başarısız]\n\n{err_detail}")

            # Sadece tüm adımlar başarılıysa çağrılır
            self.after(0, lambda: self._on_pipeline_success(str(mod_output_dir)))

        except Exception as e:
            err_msg = str(e)
            self.logger.error(f"Pipeline durduruldu: {err_msg}")
            self.after(0, lambda: self._on_pipeline_error(err_msg))

    def _translate_json_data(self, json_data, translator, cache, font_safe: bool):
        extracted_strings = []
        string_locations = []

        def collect(node, parent=None, key=None):
            if isinstance(node, str) and node.strip():
                extracted_strings.append(node)
                string_locations.append((parent, key))
            elif isinstance(node, dict):
                for k, v in node.items():
                    collect(v, node, k)
            elif isinstance(node, list):
                for idx, item in enumerate(node):
                    collect(item, node, idx)

        collect(json_data)
        if not extracted_strings:
            return json_data

        masked_items = []
        for s in extracted_strings:
            m_text, tag_map = mask_tags(s)
            masked_items.append({"original": s, "masked": m_text, "tag_map": tag_map})

        to_translate = []
        to_translate_indices = []
        cache_hits = 0
        for idx, item in enumerate(masked_items):
            cached = cache.get(item["masked"])
            if cached is not None:
                item["translated_masked"] = cached
                cache_hits += 1
            else:
                to_translate.append(item["masked"])
                to_translate_indices.append(idx)

        if cache_hits > 0:
            hit_msg = f"[INFO] [CACHE HIT] {cache_hits} satır önbellekten okundu (0 token)"
            print(hit_msg)
            self.logger.info(hit_msg)

        if to_translate:
            translations = translator.translate_batch(to_translate, batch_size=25)
            for idx, trans_text in zip(to_translate_indices, translations):
                masked_items[idx]["translated_masked"] = trans_text
                cache.set(masked_items[idx]["masked"], trans_text)

        for idx, (parent, key) in enumerate(string_locations):
            item = masked_items[idx]
            final_tr = unmask_tags(item["translated_masked"], item["tag_map"])
            if font_safe:
                final_tr = safe_font_convert(final_tr)
            parent[key] = final_tr

        return json_data

    def _on_pipeline_success(self, mod_path: str):
        self.pipeline_running = False
        self.start_btn.configure(state="normal", text="🚀 Çeviriyi ve Modlamayı Başlat")
        self._set_status("✅ Çeviri ve Mod Paketleme Başarıyla Tamamlandı!", 1.0)
        messagebox.showinfo(
            "İşlem Tamamlandı", 
            f"Tüm çeviri ve modlama işlemleri başarıyla tamamlandı!\n\nMod Çıktı Konumu:\n{mod_path}"
        )

    def _on_pipeline_error(self, err_msg: str):
        self.pipeline_running = False
        self.start_btn.configure(state="normal", text="🚀 Çeviriyi ve Modlamayı Başlat")
        self._set_status("❌ İşlem Başarısız Oldu!", 0.0)
        messagebox.showerror(
            "Pipeline Hatası - İşlem Durduruldu", 
            f"İşlem sırasında bir hata oluştu ve süreç durduruldu:\n\n{err_msg}"
        )


if __name__ == "__main__":
    app = App()
    app.mainloop()
