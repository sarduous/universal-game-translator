# Universal AI Game Localization Framework 🌐🎮

Modüler, sıfır gecikmeli (0-latency), ekran okuma (OCR) yerine doğrudan oyunların yerel dil dosyalarını toplu olarak yapay zeka ile yerelleştiren açık uçlu oyun çeviri çatısı.

---

## ⚡ Çalışma Prensibi

Geleneksel ekran yakalama (OCR) yöntemlerinin aksine bu çatı, oyunun kendi veri paketlerini açıp metin kaynaklarını doğrudan işler:

```
[Oyun Arşivi (.pak, vb.)] ──(Unpack)──► [Metin Dosyaları (.msg, .locres)]
                                                │
                                                ▼ (Parse)
[Geri Paketleme / Mod Enjeksiyonu] ◄── [Context-Aware LLM Batch Çeviri] ◄── [Temiz JSON / Metin]
```

1. **Unpack (Paket Açma):** Oyun motoruna ait arşiv dosyasından metin içeriklerinin çıkarılması.
2. **Parse (Ayrıştırma):** İkili (binary) dil dosyalarının düzenlenebilir JSON/CSV formatına dönüştürülmesi.
3. **LLM Batch Çeviri (Bağlam Duyarlı):** Terim tutarlılığı (glossary) ve oyun içi bağlam korunarak çoklu LLM modelleri ile toplu çeviri.
4. **Repack (Geri Paketleme):** Çevrilen metinlerin orijinal binary formatına geri derlenmesi ve oyun mod dizinine enjeksiyonu.

---

## 🧩 Modüler Mimari

- **Core Orchestrator:** Çeviri kuyruğu, LLM bağlantısı, önbellekleme (caching) ve bağlam yönetimini yürüten ortak çekirdek.
- **Engine Adapters (Motor Adaptörleri):**
  - ✅ **RE Engine Adapter (Capcom - v0.1):** `REE.PAK.Tool` ve `REMSG_Converter` entegrasyonu ile Resident Evil, Monster Hunter, Dragon's Dogma 2 vb. oyunlar için tam destek.
  - ⏳ **Unreal Engine Adapter (.locres) [Planlandı]:** UE4/UE5 yerelleştirme dosyaları desteği.
  - ⏳ **Unity Adapter (.assets / TextAsset / UnityPy) [Planlandı]:** Unity tabanlı oyunlar için metin ayıklama ve yeniden paketleme desteği.

---

## 🛠️ Araçlar & Gereksinimler

- **Python 3.10+**
- **Git**
- **tools/ klasörü altındaki yardımcılar:**
  - `REE.Unpacker.exe` + `Projects/` listeleri
  - `REMSG_Converter` (Git Submodule)
