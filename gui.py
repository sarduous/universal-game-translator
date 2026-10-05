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
from core.translator import GeminiTranslator
from adapters.re_engine import REEngineAdapter
from adapters.base import BaseEngineAdapter

# .env yükle
load_dotenv()

# CustomTkinter varsayılan görünüm
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


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

        self.title("Universal AI Game Translator - Modern GUI")
        self.geometry("860x740")
        self.minsize(800, 680)

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
        header_frame = ctk.CTkFrame(self, corner_radius=10, fg_color="#1E1E2E")
        header_frame.grid(row=0, column=0, padx=15, pady=(15, 10), sticky="ew")
        header_frame.grid_columnconfigure(0, weight=1)

        title_label = ctk.CTkLabel(
            header_frame, 
            text="⚔️ Universal AI Game Translator", 
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="#89B4FA"
        )
        title_label.grid(row=0, column=0, padx=15, pady=(10, 2), sticky="w")

        subtitle_label = ctk.CTkLabel(
            header_frame, 
            text="Yapay Zeka Destekli Otomatik Oyun Yerelleştirme ve Modlama Platformu", 
            font=ctk.CTkFont(size=12),
            text_color="#CDD6F4"
        )
        subtitle_label.grid(row=1, column=0, padx=15, pady=(0, 10), sticky="w")

    def _build_engine_section(self):
        engine_frame = ctk.CTkFrame(self, corner_radius=10)
        engine_frame.grid(row=1, column=0, padx=15, pady=5, sticky="ew")
        engine_frame.grid_columnconfigure(1, weight=1)

        # Başlık
        sec_title = ctk.CTkLabel(engine_frame, text="🎮 Oyun ve Motor Yapılandırması", font=ctk.CTkFont(size=14, weight="bold"))
        sec_title.grid(row=0, column=0, columnspan=3, padx=15, pady=(10, 5), sticky="w")

        # Motor Seçimi Dropdown
        ctk.CTkLabel(engine_frame, text="Oyun Motoru:").grid(row=1, column=0, padx=15, pady=5, sticky="w")
        self.engine_dropdown = ctk.CTkOptionMenu(
            engine_frame, 
            values=["RE Engine (Capcom)", "Unreal Engine (Yakında)", "Unity (Yakında)"]
        )
        self.engine_dropdown.grid(row=1, column=1, columnspan=2, padx=15, pady=5, sticky="ew")
        self.engine_dropdown.set("RE Engine (Capcom)")

        # PAK Arşiv Seçimi
        ctk.CTkLabel(engine_frame, text="PAK / Arşiv Dosyası:").grid(row=2, column=0, padx=15, pady=5, sticky="w")
        self.pak_entry = ctk.CTkEntry(engine_frame, placeholder_text="Oyun .pak dosya yolunu seçin...")
        self.pak_entry.grid(row=2, column=1, padx=(15, 5), pady=5, sticky="ew")
        self.pak_browse_btn = ctk.CTkButton(engine_frame, text="Gözat...", width=90, command=self._browse_pak_file)
        self.pak_browse_btn.grid(row=2, column=2, padx=(5, 15), pady=5)

        # Proje / Liste Etiketi
        ctk.CTkLabel(engine_frame, text="Proje / Liste Etiketi:").grid(row=3, column=0, padx=15, pady=5, sticky="w")
        self.list_file_entry = ctk.CTkEntry(engine_frame)
        self.list_file_entry.insert(0, "OWOTS_STM_Release")
        self.list_file_entry.grid(row=3, column=1, columnspan=2, padx=15, pady=5, sticky="ew")

        # Çıktı Klasörü Seçimi
        ctk.CTkLabel(engine_frame, text="Çıktı Klasörü:").grid(row=4, column=0, padx=15, pady=5, sticky="w")
        self.out_dir_entry = ctk.CTkEntry(engine_frame)
        self.out_dir_entry.insert(0, str(Path("./output").resolve()))
        self.out_dir_entry.grid(row=4, column=1, padx=(15, 5), pady=(5, 10), sticky="ew")
        self.out_dir_browse_btn = ctk.CTkButton(engine_frame, text="Gözat...", width=90, command=self._browse_output_dir)
        self.out_dir_browse_btn.grid(row=4, column=2, padx=(5, 15), pady=(5, 10))

    def _build_options_section(self):
        options_frame = ctk.CTkFrame(self, corner_radius=10)
        options_frame.grid(row=2, column=0, padx=15, pady=5, sticky="ew")
        options_frame.grid_columnconfigure(1, weight=1)

        # Font Güvenli Mod Checkbox
        self.font_safe_var = ctk.BooleanVar(value=False)
        self.font_safe_checkbox = ctk.CTkCheckBox(
            options_frame, 
            text="Font Güvenli Mod (Türkçe karakterleri güvenli harflere dönüştür: ç->c, ş->s vb.)",
            variable=self.font_safe_var,
            font=ctk.CTkFont(size=12)
        )
        self.font_safe_checkbox.grid(row=0, column=0, padx=15, pady=10, sticky="w")

        # API Durumu Etiketi
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key and api_key != "your_key_here":
            api_status_text = "🟢 Gemini API Key Tanımlı (Hazır)"
            api_status_color = "#A6E3A1"
        else:
            api_status_text = "🔴 Gemini API Key Bulunamadı (Mock Simülasyonu Modu)"
            api_status_color = "#F38BA8"

        self.api_status_label = ctk.CTkLabel(
            options_frame, 
            text=api_status_text, 
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=api_status_color
        )
        self.api_status_label.grid(row=0, column=1, padx=15, pady=10, sticky="e")

    def _build_progress_and_log_section(self):
        progress_frame = ctk.CTkFrame(self, corner_radius=10)
        progress_frame.grid(row=3, column=0, padx=15, pady=5, sticky="nsew")
        progress_frame.grid_columnconfigure(0, weight=1)
        progress_frame.grid_rowconfigure(2, weight=1)

        # Durum Metni
        self.status_label = ctk.CTkLabel(
            progress_frame, 
            text="Hazır - İşlem başlatılmayı bekliyor...", 
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#89B4FA"
        )
        self.status_label.grid(row=0, column=0, padx=15, pady=(10, 2), sticky="w")

        # İlerleme Çubuğu (Progress Bar)
        self.progress_bar = ctk.CTkProgressBar(progress_frame)
        self.progress_bar.grid(row=1, column=0, padx=15, pady=(2, 10), sticky="ew")
        self.progress_bar.set(0.0)

        # Canlı Log Kutusu (Scrollable Textbox)
        self.log_textbox = ctk.CTkTextbox(
            progress_frame, 
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="#181825",
            text_color="#A6ADC8"
        )
        self.log_textbox.grid(row=2, column=0, padx=15, pady=(0, 10), sticky="nsew")
        self.log_textbox.insert("1.0", "--- Sistem Konsolu Başlatıldı ---\n")
        self.log_textbox.configure(state="disabled")

    def _build_action_button(self):
        self.start_btn = ctk.CTkButton(
            self, 
            text="🚀 Çeviriyi ve Modlamayı Başlat", 
            font=ctk.CTkFont(size=16, weight="bold"),
            height=45,
            fg_color="#89B4FA",
            hover_color="#74C7EC",
            text_color="#11111B",
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
        self.start_btn.configure(state="disabled", text="⏳ İşlem Sürüyor...")

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
            self.logger.info("PAK Arşivi açılıyor...")
            success = adapter.extract_archive(pak_path, str(unpacked_dir), list_file=list_file)
            if not success:
                raise Exception("PAK arşivi açılırken hata oluştu!")

            # ADIM 2: JSON'a Aktarma (0.35)
            self._set_status("📄 2/5: Metinler JSON formatına aktarılıyor...", 0.35)
            self.logger.info("Ham metinler JSON'a aktarılıyor...")
            adapter.export_to_json(str(unpacked_dir), str(exported_json_dir))

            # ADIM 3: Çeviri (0.70)
            self._set_status("🤖 3/5: Yapay zeka diyalogları çeviriyor...", 0.70)
            self.logger.info("Çekirdek çeviri motoru çalıştırılıyor...")
            
            with TranslationCache("translation_cache.db") as cache:
                json_files = list(exported_json_dir.rglob("*.json"))
                for json_file in json_files:
                    with open(json_file, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    # Çeviri işlemi
                    translated_data = self._translate_json_data(data, translator, cache, font_safe)

                    rel_path = json_file.relative_to(exported_json_dir)
                    out_file = translated_json_dir / rel_path
                    out_file.parent.mkdir(parents=True, exist_ok=True)

                    with open(out_file, "w", encoding="utf-8") as f:
                        json.dump(translated_data, f, ensure_ascii=False, indent=2)

            # ADIM 4: MSG Derleme (0.85)
            self._set_status("⚙️ 4/5: Çevrilmiş metinler ikili formata (MSG) derleniyor...", 0.85)
            self.logger.info("JSON -> MSG derleme başlatılıyor...")
            adapter.import_from_json(str(translated_json_dir), str(compiled_msg_dir), original_msg_dir=str(unpacked_dir))

            # ADIM 5: Mod Paketi Oluşturma (1.00)
            self._set_status("🎁 5/5: Mod paketi oluşturuluyor...", 1.00)
            self.logger.info("Mod paketi yapılandırılıyor...")
            adapter.build_mod_package(str(compiled_msg_dir), str(mod_output_dir))

            self.after(0, lambda: self._on_pipeline_success(str(mod_output_dir)))

        except Exception as e:
            self.logger.error(f"Hata oluştu: {e}")
            self.after(0, lambda: self._on_pipeline_error(str(e)))

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
        for idx, item in enumerate(masked_items):
            cached = cache.get(item["masked"])
            if cached is not None:
                item["translated_masked"] = cached
            else:
                to_translate.append(item["masked"])
                to_translate_indices.append(idx)

        if to_translate:
            translations = translator.translate_batch(to_translate, batch_size=20)
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
        messagebox.showerror("Hata", f"İşlem sırasında bir hata oluştu:\n{err_msg}")


if __name__ == "__main__":
    app = App()
    app.mainloop()
