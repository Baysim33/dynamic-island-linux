# Spotify-Island 🏝️🔥
> Linux KDE Plasma 6 (Wayland) için Apple Dynamic Island & Soldan Rüzgarlı Kül/Toz Albüm Geçiş Sistemi.

---

## ✨ Özellikler

1. **Dinamik Ada (Dynamic Island) Durumları:**
   * **Gizli (Kapalı):** Müzik durduğunda veya Spotify kapalıyken çentik tamamen kaybolur, ekranda sıfır yer kaplar.
   * **Kompakt Mod (Şarkı Çalarken):** Ekranın en üst ortasında mat siyah, minimalist bir hap belirir. Solunda albüm resmi, sağında müziğin ritmine göre canlı dalgalanan **neon yeşil ses dalgaları (audio wave visualizer)** dans eder.
   * **Genişlemiş Mod (Şarkı Değiştiğinde):** Çentik pürüzsüzce aşağı ve yanlara doğru büyür.
     * **🌪️ Soldan Rüzgar Vurmuş Kül Efekti:** Eski albüm kapağı soldan esen şiddetli bir rüzgarla binlerce minik kül, duman ve akkor kor kıvılcımına ayrılarak sağa-yukarı doğru savrulup yok olur.
     * Yeni albüm kapağının pikselleri boşluktan girdap gibi merkeze çekilerek (manyetik montaj) birleşir ve netleşir!
     * Şarkının adı, sanatçısı ve albümü yanında görünür.
     * 4.5 saniye sonra ada tekrar zarifçe kompakt (ses dalgası) moduna küçülür.

2. **Çift Monitör & Akıllı Oyun Koruması:**
   * **HDMI-A-2 (240Hz Ana Monitör)** ve **HDMI-A-1 (75Hz Yan Monitör)** desteklenir.
   * Steam, Proton, Wine veya tam ekran bir oyun açıldığında çentik oyunu kapatmamak için **otomatik olarak diğer boş monitörün üstüne geçer!** Oyun bittiğinde tekrar 240Hz monitörünüze geri döner.

3. **Etkileşim:**
   * Çentiğe sol tıklandığında Spotify'ı Oynatır / Duraklatır.
   * Fareyle üzerine gelindiğinde küçülme sayacı durur, albümü ve parçacıkları rahatça izleyebilirsiniz.

---

## 🛠️ Servis Komutları

Servisi kontrol etmek veya yeniden başlatmak için:
```bash
# Durum kontrolü
systemctl --user status spotify-island.service

# Yeniden başlatma
systemctl --user restart spotify-island.service

# Durdurma
systemctl --user stop spotify-island.service
```
