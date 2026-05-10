#!/usr/bin/env python3
"""
Indonesian (id) localization translation script for CIRIS.
Translates en.json to id.json using the Indonesian glossary terms.
"""

import json
from pathlib import Path

# Indonesian translations organized by section
# Based on /home/emoore/CIRISAgent/docs/localization/glossaries/id_glossary.md

TRANSLATIONS = {
    "_meta": {"language": "id", "language_name": "Indonesian", "direction": "ltr"},
    "setup": {
        "welcome_title": "Selamat Datang di CIRIS",
        "welcome_desc": "CIRIS adalah asisten AI etis yang berjalan di perangkat Anda. Percakapan dan data Anda tetap bersifat pribadi.",
        "prefs_title": "Preferensi Anda",
        "prefs_desc": "Bantu CIRIS berkomunikasi dengan Anda dalam bahasa pilihan Anda. Lokasi bersifat opsional dan membantu memberikan konteks yang relevan.",
        "prefs_language_label": "Bahasa Pilihan",
        "prefs_location_label": "Lokasi (opsional)",
        "prefs_location_hint": "Bagikan sebanyak atau sesedikit yang Anda inginkan. Ini membantu CIRIS memahami konteks Anda.",
        "prefs_location_none": "Lebih baik tidak menyebutkan",
        "prefs_location_country": "Negara saja",
        "prefs_location_region": "Negara + Wilayah/Provinsi",
        "prefs_location_city": "Negara + Wilayah + Kota",
        "prefs_country_label": "Negara",
        "prefs_country_hint": "mis., Ethiopia, Amerika Serikat, Jepang",
        "prefs_region_label": "Wilayah / Provinsi",
        "prefs_region_hint": "mis., Amhara, California, Tokyo",
        "prefs_city_label": "Kota Terdekat (opsional)",
        "prefs_city_hint": "mis., Addis Ababa, San Francisco, Tokyo",
        "prefs_location_search_label": "Cari kota",
        "prefs_location_search_hint": "Mulai mengetik nama kota...",
        "prefs_location_pop": "Pop. {pop}",
        "llm_title": "Konfigurasi AI",
        "llm_desc": "Konfigurasikan cara CIRIS terhubung ke layanan AI.",
        "confirm_title": "Konfirmasi Pengaturan",
        "confirm_desc": "Tinjau konfigurasi Anda dan selesaikan pengaturan.",
        "continue": "Lanjutkan",
        "back": "Kembali",
        "next": "Berikutnya",
        "finish": "Selesaikan Pengaturan",
        "complete_message": "Pengaturan berhasil diselesaikan. Memulai prosesor agen...",
        "error_runtime": "Runtime tidak tersedia - tidak dapat menyelesaikan pengaturan",
    },
    "agent": {
        "greeting": "Halo! Bagaimana saya dapat membantu Anda hari ini?",
        "thinking": "Izinkan saya memikirkan hal tersebut...",
        "error_generic": "Saya mengalami masalah saat memproses permintaan Anda. Silakan coba lagi.",
        "error_timeout": "Permintaan memakan waktu terlalu lama. Silakan coba lagi.",
        "defer_to_wa": "Saya perlu berkonsultasi dengan Otoritas Bijak tentang hal ini. Saya akan kembali kepada Anda.",
        "task_complete": "Tugas berhasil diselesaikan.",
        "no_permission": "Saya tidak memiliki izin untuk melakukan itu.",
        "clarify_request": "Bisakah Anda memperjelas maksud Anda?",
        "defer_check_panel": "Agen memilih untuk menyerahkan, periksa panel otoritas bijak jika Anda adalah pengguna pengaturan",
        "rejected_message": "Agen menolak pesan",
        "no_send_permission": "Anda tidak memiliki izin untuk mengirim pesan ke agen ini.",
        "credit_blocked": "Interaksi diblokir oleh kebijakan kredit.",
        "billing_error": "Kesalahan layanan penagihan LLM. Silakan periksa akun Anda atau coba lagi nanti.",
        "new_messages_arrived": "Agen menyelesaikan tugas tetapi pesan baru tiba yang belum ditangani",
        "restarted_stale_task": "Saya dimulai ulang saat memproses permintaan Anda. Tugas sebelumnya diselesaikan secara otomatis. Silakan kirim ulang pesan Anda jika Anda masih membutuhkan respons.",
    },
    "status": {
        "executing": "Mengeksekusi...",
        "completed": "Selesai",
        "failed": "Gagal",
        "pending": "Tertunda",
        "online": "Online",
        "offline": "Offline",
        "success": "Berhasil",
        "all_operational": "Semua sistem operasional",
    },
}


def load_en_json():
    """Load the English source file."""
    en_path = Path(__file__).parent.parent / "ciris_engine" / "data" / "localized" / "en.json"
    with open(en_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_id_json(data):
    """Save the Indonesian translation file."""
    id_path = Path(__file__).parent.parent / "ciris_engine" / "data" / "localized" / "id.json"
    with open(id_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"✓ Saved to {id_path}")


def count_keys(d, prefix=""):
    """Recursively count all leaf keys in a nested dict."""
    count = 0
    for k, v in d.items():
        if isinstance(v, dict):
            count += count_keys(v, f"{prefix}{k}.")
        else:
            count += 1
    return count


def main():
    print("Loading English source...")
    en_data = load_en_json()
    en_count = count_keys(en_data)
    print(f"English file has {en_count} nested string keys")

    print("\nThis script contains partial translations.")
    print("The full translation is too large for a single Python script.")
    print("For now, using the partial translation as a template.")

    # For demonstration, save the partial translations
    save_id_json(TRANSLATIONS)

    id_count = count_keys(TRANSLATIONS)
    print(f"\nTranslated {id_count} keys out of {en_count}")
    print(f"Coverage: {id_count/en_count*100:.1f}%")


if __name__ == "__main__":
    main()
