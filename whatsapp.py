import sys
import asyncio
import re
import aiohttp
import logging
from telethon import TelegramClient, events
import time
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains

# -----------------------------------------------------------------------------
# 1) BMP Dışı Karakterleri Temizleme Fonksiyonu
def remove_non_bmp_characters(text: str) -> str:
    """
    ChromeDriver'ın desteklemediği BMP dışı (U+FFFF üstü) karakterleri kaldırır.
    """
    return ''.join(ch for ch in text if ord(ch) <= 0xFFFF)

# -----------------------------------------------------------------------------
# Global variable for persistent WhatsApp Web driver
global_whatsapp_driver = None

def get_whatsapp_driver():
    r"""
    Eğer global driver yoksa, yeni bir Chrome driver oluşturur.
    Kullanıcı profil klasörü (ör. C:\whatsapp_profile) kullanılarak, önceki oturum korunur.
    """
    global global_whatsapp_driver
    if global_whatsapp_driver is None:
        options = Options()
        options.add_argument("user-data-dir=C:\\whatsapp_profile")
        service = Service("C:\\chromedriver-win64\\chromedriver.exe")
        driver = webdriver.Chrome(service=service, options=options)
        driver.get("https://web.whatsapp.com")
        try:
            WebDriverWait(driver, 60).until(
                EC.presence_of_element_located((By.XPATH, "//div[@contenteditable='true'][@data-tab='3']"))
            )
        except Exception as e:
            logging.error("WhatsApp Web yüklenirken hata: " + str(e))
            driver.quit()
            return None
        global_whatsapp_driver = driver
    return global_whatsapp_driver

def send_message_whatsapp(message, target_chat):
    logging.info("[DEBUG] send_message_whatsapp() fonksiyonu başladı.")
    driver = get_whatsapp_driver()
    if driver is None:
        logging.error("[DEBUG] WhatsApp driver alınamadı, fonksiyon sonlanıyor.")
        return

    wait = WebDriverWait(driver, 60)
    try:
        logging.info("[DEBUG] Arama kutusunu bulmaya çalışıyorum...")
        search_box = wait.until(EC.presence_of_element_located(
            (By.XPATH, "//div[@contenteditable='true'][@data-tab='3']")))
        logging.info("[DEBUG] Arama kutusu bulundu.")
        search_box.click()
        search_box.clear()
        search_box.send_keys(target_chat)
        time.sleep(2)
        
        logging.info(f"[DEBUG] '{target_chat}' sohbetini arıyorum...")
        chat = None
        chat_selectors = [
            ("xpath", f"//span[@title='{target_chat}']"),
            ("xpath", f"//*[@id='pane-side']//span[contains(text(), '{target_chat}')]")
        ]
        for method, selector in chat_selectors:
            try:
                chat = wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
                if chat:
                    logging.info(f"[DEBUG] Sohbet bulundu: {selector}")
                    break
            except Exception as e:
                logging.warning(f"[DEBUG] {selector} ile sohbet bulunamadı: {e}")
        if chat is None:
            raise Exception("Hedef sohbet bulunamadı.")
        
        logging.info("[DEBUG] Sohbet bulundu, tıklamayı native click ile deniyorum...")
        try:
            chat.click()
        except Exception as native_e:
            logging.warning(f"[DEBUG] Native click hata verdi: {native_e}. ActionChains ile deniyorum...")
            ActionChains(driver).move_to_element(chat).click().perform()
        time.sleep(8)  # Sohbetin tamamen açılması için bekleme
        
        try:
            search_box.send_keys(Keys.ESCAPE)
        except Exception as e:
            logging.warning("[DEBUG] Arama kutusu temizlenemedi: " + str(e))
        time.sleep(1)
    except Exception as e:
        logging.error("[DEBUG] Hedef sohbet bulunamadı: " + str(e))
        return

    try:
        logging.info("[DEBUG] Mesaj kutusunu bulmaya çalışıyorum...")
        message_box = None
        selectors = [
            ("css", "div[data-testid='conversation-compose-box-input']"),
            ("xpath", "//div[@contenteditable='true'][@data-tab='10']"),
            ("xpath", "//div[@contenteditable='true'][@data-tab='6']"),
            ("xpath", "//footer//div[@contenteditable='true']"),
            ("xpath", "//div[@title='Bir mesaj yaz']"),
            ("xpath", "//div[@title='Bir mesaj yazın']"),
            ("xpath", "//div[@title='Mesaj']"),
            ("xpath", "//*[@id='main']/footer/div[1]/div/span/div/div[2]/div[1]/div[2]/div[1]"),
            ("xpath", "//div[@role='textbox' and @contenteditable='true']")
        ]
        for method, selector in selectors:
            logging.info(f"[DEBUG] {method.upper()} seçici deniyorum: {selector}")
            try:
                if method == "css":
                    mb = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, selector)))
                else:
                    mb = wait.until(EC.visibility_of_element_located((By.XPATH, selector)))
                if mb:
                    message_box = mb
                    logging.info(f"[DEBUG] Mesaj kutusu bulundu: {selector}")
                    break
            except Exception as inner_e:
                logging.warning(f"[DEBUG] {method.upper()} seçici {selector} ile mesaj kutusu bulunamadı: {inner_e}")
        
        if not message_box:
            raise Exception("Mesaj kutusu bulunamadı, lütfen seçici değerlerini güncelleyin.")
        
        logging.info("[DEBUG] Mesaj kutusu bulundu, BMP dışı karakterleri temizliyorum...")
        safe_message = remove_non_bmp_characters(message)
        logging.info(f"[DEBUG] Gönderilecek mesaj: {safe_message}")

        logging.info("[DEBUG] Mesaj kutusuna tıklayıp, mesajı yazmaya başlıyorum...")
        try:
            message_box.click()
        except Exception:
            driver.execute_script("arguments[0].click();", message_box)
        time.sleep(1)
        message_box.send_keys(safe_message)
        time.sleep(0.5)
        message_box.send_keys(Keys.ENTER)
        logging.info("WhatsApp mesajı gönderildi.")
    except Exception as e:
        logging.error("WhatsApp mesajı gönderilemedi: " + str(e))

# -----------------------------------------------------------------------------
# Loglama Ayarları: Hem dosyaya hem de ekrana log (UTF-8 kodlamalı)
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("telegram_bot.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)

# -----------------------------------------------------------------------------
# Telegram API Bilgileri
api_id = 20642723
api_hash = "6c5e7c19f3a701201707ee28da0a40f6"
session_name = "amznbbt"
phone_number = "306940656110"  # Ülke kodu ile tam numara

# -----------------------------------------------------------------------------
# Telegram Kaynak Kanalları (Sadece aşağıdaki üç kanal)
SOURCE_CHANNELS = [
    "@couponsundrabatte2",
    "@Beauty_Schoenheit",
    "@bbtamazontest"
]

# -----------------------------------------------------------------------------
# Amazon Affiliate Ayarları
AFFILIATE_TAG = "bbtdeals0d-21"

# -----------------------------------------------------------------------------
# WhatsApp Hedef Sohbet Adı (WhatsApp Web’de göründüğü gibi)
TARGET_WHATSAPP_CHAT = "Test bbtdeals"

# -----------------------------------------------------------------------------
# Amazon Link İşleme Sınıfı
class AmazonLinkProcessor:
    """
    Amazon linklerini açıp yönlendirmeleri takip eder,
    ürün ID'sini (ASIN) çıkarır ve affiliate link formatına dönüştürür.
    Format: https://www.amazon.de/dp/<PRODUCT_ID>?tag=AFFILIATE_TAG
    """
    def __init__(self, affiliate_tag, session):
        self.affiliate_tag = affiliate_tag
        self.session = session

    async def get_final_url(self, url: str) -> str:
        try:
            async with self.session.get(url, timeout=10, allow_redirects=True) as response:
                final_url = str(response.url)
                logging.info(f"🔄 Çözümlenen Link: {url} ➝ {final_url}")
                return final_url
        except Exception as e:
            logging.error(f"🔴 get_final_url hata: {e} - URL: {url}")
            return None

    def extract_product_id(self, url: str) -> str:
        patterns = [
            r'(?:/dp/|/gp/product/)([A-Z0-9]{10})',
            r'asin=([A-Z0-9]{10})'
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                product_id = match.group(1)
                logging.info(f"Ürün ID'si bulundu: {product_id}")
                return product_id
        logging.error(f"Ürün ID'si bulunamadı: {url}")
        return None

    def generate_affiliate_url(self, product_id: str) -> str:
        return f"https://www.amazon.de/dp/{product_id}?tag={self.affiliate_tag}"

    async def process_amazon_link(self, link: str) -> str:
        logging.info(f"🔄 Amazon link işleniyor: {link}")
        final_url = await self.get_final_url(link)
        if not final_url:
            logging.error("🔴 Amazon linki çözümlenemedi.")
            return None

        product_id = self.extract_product_id(final_url)
        if not product_id:
            logging.error(f"🔴 Ürün ID'si bulunamadı. Final URL: {final_url}")
            return None

        affiliate_url = self.generate_affiliate_url(product_id)
        logging.info(f"✅ Affiliate Link oluşturuldu: {affiliate_url}")
        return affiliate_url

# -----------------------------------------------------------------------------
# Telegram Giriş ve Doğrulama Fonksiyonu
async def login_to_telegram():
    client = TelegramClient(session_name, api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        logging.info("🔵 Doğrulama kodu gönderiliyor...")
        await client.send_code_request(phone_number)
        code = input("📌 Telegram doğrulama kodunu girin: ")
        try:
            await client.sign_in(phone_number, code)
            logging.info("✅ Başarıyla giriş yapıldı!")
        except Exception as e:
            logging.error(f"🔴 Giriş hatası: {e}")
    else:
        logging.info("✅ Oturum zaten yetkilendirilmiş.")
    return client

# -----------------------------------------------------------------------------
# Telegram Mesajını İşleyip WhatsApp'a Gönderen Fonksiyonu
async def forward_message(message, client, processor):
    try:
        text = getattr(message, "raw_text", None) or (message.text or message.caption or "")
        if not text:
            logging.warning("⚠ Gelen mesajda okunabilir metin bulunamadı.")
            return
        else:
            logging.info(f"📥 Mesaj yakalandı (kaynak kanal): {message.chat_id if message.chat_id else 'Bilinmiyor'}")
            logging.info("📄 Orijinal mesaj içeriği:\n" + text)
        
        pattern = r"(https?://(?:www\.)?(?:amazon\.de|amzn\.to|amzn\.eu)[^\s]+)"
        found_links = re.findall(pattern, text)
        logging.info(f"🔍 Mesajda bulunan link adedi: {len(found_links)}")
        if found_links:
            logging.info("🔍 Tespit edilen linkler: " + ", ".join(found_links))
            conversion_failed = False
            for link in found_links:
                affiliate_link = await processor.process_amazon_link(link)
                if affiliate_link:
                    text = text.replace(link, affiliate_link)
                    logging.info(f"✏️ Link dönüştürüldü: {link} -> {affiliate_link}")
                else:
                    logging.error(f"🚨 Affiliate link oluşturulamadı: {link}")
                    conversion_failed = True
            if conversion_failed:
                logging.error("🚨 Bazı linkler dönüştürülemediği için mesaj gönderilmiyor.")
                return
        else:
            logging.info("🔍 Mesajda Amazon linki bulunamadı. Mesaj gönderilmiyor.")
            return
        
        logging.info("💬 Dönüştürülmüş mesaj içeriği:\n" + text)
        await asyncio.to_thread(send_message_whatsapp, text, TARGET_WHATSAPP_CHAT)
    except Exception as e:
        logging.error(f"🔴 Mesaj işleme hatası: {e}")

# -----------------------------------------------------------------------------
# Botu Çalıştıran Fonksiyon: Telegram'dan mesajları dinler
async def start_bot():
    client = await login_to_telegram()
    async with aiohttp.ClientSession() as aiohttp_session:
        processor = AmazonLinkProcessor(AFFILIATE_TAG, aiohttp_session)
        
        @client.on(events.NewMessage(chats=SOURCE_CHANNELS))
        async def channel_message_handler(event):
            logging.info("📨 Yeni mesaj alındı.")
            if event.message:
                try:
                    source = getattr(event.message.peer_id, "channel_id", "Bilinmiyor")
                    logging.info(f"📡 Mesajın geldiği kanal ID: {source}")
                except Exception as e:
                    logging.warning(f"⚠ Kaynak kanal bilgisi alınamadı: {e}")
                await forward_message(event.message, client, processor)
            else:
                logging.warning("⚠ Olayda mesaj verisi bulunamadı.")
        
        logging.info("🚀 Bot çalışıyor, mesajlar dinleniyor...")
        await client.run_until_disconnected()

# -----------------------------------------------------------------------------
# Programın Başlatılması
if __name__ == '__main__':
    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        logging.info("🛑 Program kapatılıyor...")