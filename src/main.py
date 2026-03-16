# pipeline.py

from __future__ import annotations

import argparse
import time

from .enums import SupplyCommand
from .supply_config import load_supply_profiles
from .drivers.factory import create_driver
from .transport import SerialTransport
from .config import SerialConfig
from .pipeline import SupplyPipeline


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Power Supply Automation (multi-supply, config-driven)")

    p.add_argument("port", help="Serial port (e.g., COM4)")
    p.add_argument("--config", default="power_supplies.json", help="Supply config JSON path")
    p.add_argument("--supply", default=None, help="Supply profile name (e.g., A, B). If omitted, uses config default.")

    # Shared setpoints
    p.add_argument("--volt", type=float, default=5.0, help="Output voltage setpoint (Volts)")
    p.add_argument("--curr", type=float, default=0.2, help="Output current limit setpoint (Amps)")

    # A-specific knobs (E3645A)
    p.add_argument("--range", dest="range_mode", choices=["low", "high"], default="low",
                   help="(A/E3645A) Select output range: low or high")
    p.add_argument("--ovp", type=float, default=6.0, help="(A/E3645A) OVP threshold (Volts)")
    p.add_argument("--skip-ovp", action="store_true", help="(A/E3645A) Skip OVP configuration")

    # B-specific knobs (E3631A)
    p.add_argument("--rail", choices=["P6V", "P25V", "N25V"], default="P6V",
                   help="(B/E3631A) Select output rail before VOLT/CURR: P6V, P25V, N25V")
    p.add_argument("--use-apply", action="store_true",
                   help="(B/E3631A) Use APPLY instead of separate VOLT/CURR commands (requires mapping)")

    # Common toggles
    p.add_argument("--skip-reset", action="store_true", help="Skip *RST baseline reset")
    p.add_argument("--lock-remote", action="store_true", help="Lock front panel keys in remote (SYST:RWLOCK)")

    return p.parse_args()


def run_profile_a(pipeline: SupplyPipeline, args: argparse.Namespace) -> None:
    # ---- GOLDEN PATH (A / E3645A) ----
    pipeline.execute(SupplyCommand.SYSTEM_REMOTE, expect_response=False)

    if args.lock_remote:
        pipeline.execute(SupplyCommand.SYSTEM_RWLOCK, expect_response=False)

    pipeline.execute(SupplyCommand.IDN, expect_response=True)

    if not args.skip_reset:
        pipeline.execute(SupplyCommand.RESET, expect_response=False)

    pipeline.execute(SupplyCommand.CLOSE_OUTPUT, expect_response=False)

    if args.range_mode == "low":
        pipeline.execute(SupplyCommand.SET_RANGE_LOW, expect_response=False)
    else:
        pipeline.execute(SupplyCommand.SET_RANGE_HIGH, expect_response=False)

    if not args.skip_ovp:
        pipeline.execute(SupplyCommand.OVP_SET, value=args.ovp, expect_response=False)
        pipeline.execute(SupplyCommand.OVP_ENABLE, expect_response=False)
        pipeline.execute(SupplyCommand.OVP_CLEAR, expect_response=False)

    pipeline.execute(SupplyCommand.SET_VOLTAGE, value=args.volt, expect_response=False)
    pipeline.execute(SupplyCommand.SET_CURRENT, value=args.curr, expect_response=False)

    pipeline.execute(SupplyCommand.OPEN_OUTPUT, expect_response=False)

    pipeline.execute(SupplyCommand.MEASURE_VOLTAGE, expect_response=True)
    pipeline.execute(SupplyCommand.MEASURE_CURRENT, expect_response=True)

    pipeline.execute(SupplyCommand.CLOSE_OUTPUT, expect_response=False)
    pipeline.execute(SupplyCommand.SYSTEM_LOCAL, expect_response=False)


# def run_profile_b(pipeline: SupplyPipeline, args: argparse.Namespace) -> None:
#     # ---- GOLDEN PATH (B / E3631A) ----
#     pipeline.execute(SupplyCommand.SYSTEM_REMOTE, expect_response=True)
#
#     if args.lock_remote:
#         # B profile may or may not support RWLOCK; config decides.
#         pipeline.execute(SupplyCommand.SYSTEM_RWLOCK, expect_response=True)
#
#     pipeline.execute(SupplyCommand.IDN, expect_response=True)
#
#     if not args.skip_reset:
#         pipeline.execute(SupplyCommand.RESET, expect_response=True)
#
#     pipeline.execute(SupplyCommand.CLOSE_OUTPUT, expect_response=True)
#
#     # Rail selection is mandatory for E3631A-like supplies
#     if args.rail == "P6V":
#         pipeline.execute(SupplyCommand.SELECT_P6V, expect_response=True)
#     elif args.rail == "P25V":
#         pipeline.execute(SupplyCommand.SELECT_P25V, expect_response=True)
#     else:
#         pipeline.execute(SupplyCommand.SELECT_N25V, expect_response=True)
#
#     # Setpoints
#     if args.use_apply:
#         pipeline.execute(SupplyCommand.APPLY, value=None, expect_response=True)
#     else:
#         pipeline.execute(SupplyCommand.SET_VOLTAGE, value=args.volt, expect_response=True)
#         pipeline.execute(SupplyCommand.SET_CURRENT, value=args.curr, expect_response=True)
#
#     pipeline.execute(SupplyCommand.OPEN_OUTPUT, expect_response=True)
#     pipeline.execute(SupplyCommand.MEASURE_VOLTAGE, expect_response=True)
#     pipeline.execute(SupplyCommand.MEASURE_CURRENT, expect_response=True)
#     pipeline.execute(SupplyCommand.CLOSE_OUTPUT, expect_response=True)
#     pipeline.execute(SupplyCommand.SYSTEM_LOCAL, expect_response=True)


def run_profile_b(pipeline: SupplyPipeline, args: argparse.Namespace) -> None:
    # ===============================================================
    # E3631A İnteraktif Kontrol Akışı
    # Referans: Agilent E3631A User's Guide (E3631-90002)
    # ===============================================================

    # ---- STARTUP (otomatik) ----

    # Sayfa 87 - SYST:REM: Cihazı RS-232 remote moduna alır.
    # Remote modda cihaz sadece seri port komutlarını kabul eder.
    pipeline.execute(SupplyCommand.SYSTEM_REMOTE, expect_response=False)

    # Sayfa 82 - *IDN?: Cihaz kimlik bilgisini döner.
    # Bağlantının doğru kurulduğunu teyit etmek için kullanılır.
    resp = pipeline.execute(SupplyCommand.IDN, expect_response=True)
    print(f"\nBağlı cihaz: {resp}")

    # Sayfa 82 - *RST: Cihazı fabrika varsayılanlarına sıfırlar.
    # Tüm çıkışlar 0V, akım limitleri default, output OFF, tracking OFF.
    pipeline.execute(SupplyCommand.RESET, expect_response=False)
    print("Cihaz sıfırlandı (*RST).")

    # RST sonrası *IDN? tekrar sorgulanır — bazı cihazlarda RST öncesi IDN hata verebilir.
    resp = pipeline.execute(SupplyCommand.IDN, expect_response=True)
    print(f"Bağlı cihaz (RST sonrası): {resp}")

    # Sayfa 87 - SYST:RWL: Ön panel tuşlarını kilitler.
    # Kullanıcı cihaz üzerinden müdahale edemez, sadece remote komutlar çalışır.
    panel_kilitli = False
    lock = input("\nÖn paneli kilitlemek ister misiniz? (E/H): ").strip().upper()
    if lock == "E":
        pipeline.execute(SupplyCommand.SYSTEM_RWLOCK, expect_response=False)
        panel_kilitli = True
        print("Panel kilitlendi (SYST:RWL).")

    # ---- İNTERAKTİF MENÜ ----
    # Sayfa 70-74 - Simplified Programming Overview:
    # Önce INST:SEL ile kanal seçilir, sonra VOLT/CURR ile değerler ayarlanır,
    # OUTP ON ile çıkış açılır, MEAS ile ölçüm yapılır.
    aktif_kanal = "P6V"
    
    while True:
        kilit_durum = "Kilitli" if panel_kilitli else "Açık"
        print(f"\n====== E3631A Kontrol Menüsü | Kanal: {aktif_kanal} | Ön Panel: {kilit_durum} ======")
        print("[1] Kanal seç           (P6V / P25V / N25V)")
        print("[2] Voltaj ayarla       (VOLT)")
        print("[3] Akım limiti ayarla  (OCP)")
        print("[4] Çıkışı aç           (OUTP ON)")
        print("[5] Çıkışı kapat        (OUTP OFF)")
        print("[6] Ölçüm yap           (MEAS:VOLT? + MEAS:CURR?)")
        print("[7] Hata kontrol        (SYST:ERR?)")
        print("[8] Reset               (*RST)")
        print("[0] Çıkış")
        print("===================================")

        secim = input("Seçiminiz: ").strip()

        if secim == "1":
            # Sayfa 74 - INST:SEL {P6V|P25V|N25V}:
            # Programlanacak çıkışı seçer. VOLT/CURR komutları seçili kanala uygulanır.
            # P6V=Kanal1 (0-6.18V, 0-5.15A), P25V=Kanal2 (0-25.75V, 0-1.03A),
            # N25V=Kanal3 (0 ile -25.75V, 0-1.03A)  [Sayfa 72, Table 4-1]
            print("  [1] P6V  (+6V,  max 5.15A)")
            print("  [2] P25V (+25V, max 1.03A)")
            print("  [3] N25V (-25V, max 1.03A)")
            kanal = input("  Kanal: ").strip()
            if kanal == "1":
                pipeline.execute(SupplyCommand.SELECT_P6V, expect_response=False)
                aktif_kanal = "P6V"
                print("  Kanal: P6V seçildi.")
            elif kanal == "2":
                pipeline.execute(SupplyCommand.SELECT_P25V, expect_response=False)
                aktif_kanal = "P25V"
                print("  Kanal: P25V seçildi.")
            elif kanal == "3":
                pipeline.execute(SupplyCommand.SELECT_N25V, expect_response=False)
                aktif_kanal = "N25V"
                print("  Kanal: N25V seçildi.")
            else:
                print("  Geçersiz seçim.")

        elif secim == "2":
            # Sayfa 78 - VOLT {value}: Seçili kanalın voltaj limitini ayarlar.
            # Değer kanalın aralığında olmalı (Table 4-1).
            try:
                volt = float(input("  Voltaj (V): ").strip())
                pipeline.execute(SupplyCommand.SET_VOLTAGE, value=volt, expect_response=False)
                print(f"  Voltaj {volt}V olarak ayarlandı.")
            except ValueError:
                print("  Geçersiz değer.")

        elif secim == "3":
            # Sayfa 80 - CURR:PROT {value}: OCP seviyesini ayarlar.
            # CURR:PROT:STAT ON/OFF ile OCP aktif/pasif edilir.
            print("  OCP: Belirlenen akım sınırı aşılırsa çıkışı otomatik kapatır.")
            print("  [1] OCP sınır değeri ayarla ve aktif et")
            print("  [2] OCP kapat")
            ocp_secim = input("  Seçiminiz: ").strip()
            if ocp_secim == "1":
                try:
                    ocp = float(input("  OCP akım limiti (A): ").strip())
                    pipeline.execute(SupplyCommand.OCP_SET, value=ocp, expect_response=False)
                    pipeline.execute(SupplyCommand.OCP_ENABLE, expect_response=False)
                    print(f"  OCP {ocp}A olarak ayarlandı ve aktif edildi.")
                except ValueError:
                    print("  Geçersiz değer.")
            elif ocp_secim == "2":
                pipeline.execute(SupplyCommand.OCP_DISABLE, expect_response=False)
                print("  OCP kapatıldı.")
            else:
                print("  Geçersiz seçim.")

        elif secim == "4":
            # Sayfa 77 - OUTP ON: Üç çıkışı birden aktif eder.
            pipeline.execute(SupplyCommand.OPEN_OUTPUT, expect_response=False)
            print("  Çıkış açıldı (OUTP ON).")
            time.sleep(0.5)  # Çıkış stabilize olana kadar bekle
            v = pipeline.execute(SupplyCommand.MEASURE_VOLTAGE, expect_response=True)
            c = pipeline.execute(SupplyCommand.MEASURE_CURRENT, expect_response=True)
            print(f"  Ölçüm -> Voltaj: {v} V, Akım: {c} A")

        elif secim == "5":
            # Sayfa 77 - OUTP OFF: Üç çıkışı birden kapatır.
            pipeline.execute(SupplyCommand.CLOSE_OUTPUT, expect_response=False)
            print("  Çıkış kapatıldı (OUTP OFF).")

        elif secim == "6":
            # Sayfa 76 - MEAS:VOLT? / MEAS:CURR?: Seçili kanalın gerçek
            # çıkış voltajını ve akımını ölçer.
            v = pipeline.execute(SupplyCommand.MEASURE_VOLTAGE, expect_response=True)
            c = pipeline.execute(SupplyCommand.MEASURE_CURRENT, expect_response=True)
            print(f"  Ölçüm -> Voltaj: {v} V, Akım: {c} A")

        elif secim == "7":
            # Sayfa 82 - SYST:ERR?: Hata kuyruğundaki hatayı döner (FIFO).
            # Her sorgu bir hata çeker. "+0, No error" gelene kadar döngüyle okunur.
            print("  Hata kuyruğu okunuyor...")
            hata_sayisi = 0
            while True:
                err = pipeline.execute(SupplyCommand.SYSTEM_ERROR, expect_response=True)
                if err is None or "+0" in str(err):
                    break
                hata_sayisi += 1
                print(f"  [{hata_sayisi}] {err}")
            if hata_sayisi == 0:
                print("  Hata yok.")
            else:
                print(f"  Toplam {hata_sayisi} hata okundu, kuyruk temizlendi.")

        elif secim == "8":
              # Sayfa 82 - *RST: Cihazı fabrika varsayılanlarına sıfırlar.
              # Tüm çıkışlar 0V, akım limitleri default (P6V=5A, ±25V=1A),
              # output OFF, tracking OFF. Kanal P6V'ye döner.
              pipeline.execute(SupplyCommand.RESET, expect_response=False)
              aktif_kanal = "P6V"
              ocp_esik = None
              print("  Cihaz sıfırlandı (*RST). Kanal P6V'ye döndü, OCP sıfırlandı.")

        elif secim == "0":
            # Güvenli kapanış:
            # Sayfa 77 - OUTP OFF: Çıkışları kapat
            # Sayfa 87 - SYST:LOC: Cihazı local moda döndürür, ön panel aktif olur
            pipeline.execute(SupplyCommand.CLOSE_OUTPUT, expect_response=False)
            pipeline.execute(SupplyCommand.SYSTEM_LOCAL, expect_response=False)
            if panel_kilitli:
                print("\nÖn panel kilidi açıldı (SYST:LOC).")
            print("Çıkışlar kapatıldı, cihaz local moda döndü. Güle güle!")
            break

        else:
            print("  Geçersiz seçim, tekrar deneyin.")


def main() -> int:
    args = parse_args()

    default_name, profiles = load_supply_profiles(args.config)
    supply_name = args.supply or default_name

    if supply_name not in profiles:
        available = ", ".join(sorted(profiles.keys()))
        raise SystemExit(f"Unknown supply profile '{supply_name}'. Available: {available}")

    profile = profiles[supply_name]

    cfg: SerialConfig = SerialConfig(
        port=args.port,
        baudrate=profile.serial.baudrate,
        bytesize=profile.serial.bytesize,
        parity=profile.serial.parity,
        stopbits=profile.serial.stopbits,
        timeout_s=profile.serial.timeout_s,
        write_timeout_s=profile.serial.write_timeout_s,
        newline=profile.serial.newline,
    )

    transport = SerialTransport(cfg)
    driver = create_driver(profile)
    pipeline = SupplyPipeline(transport=transport, driver=driver)

    transport.open()
    try:
        if supply_name == "A":
            run_profile_a(pipeline, args)
        elif supply_name == "B":
            run_profile_b(pipeline, args)
        else:
            # Default behavior: minimal common sequence
            pipeline.execute(SupplyCommand.SYSTEM_REMOTE, expect_response=False)
            pipeline.execute(SupplyCommand.IDN, expect_response=True)
            pipeline.execute(SupplyCommand.CLOSE_OUTPUT, expect_response=False)
            pipeline.execute(SupplyCommand.SET_VOLTAGE, value=args.volt, expect_response=False)
            pipeline.execute(SupplyCommand.SET_CURRENT, value=args.curr, expect_response=False)
            pipeline.execute(SupplyCommand.OPEN_OUTPUT, expect_response=False)
            pipeline.execute(SupplyCommand.MEASURE_VOLTAGE, expect_response=True)
            pipeline.execute(SupplyCommand.MEASURE_CURRENT, expect_response=True)
            pipeline.execute(SupplyCommand.CLOSE_OUTPUT, expect_response=False)
            pipeline.execute(SupplyCommand.SYSTEM_LOCAL, expect_response=False)

    finally:
        transport.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
