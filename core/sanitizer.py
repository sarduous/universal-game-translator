import re

class TagSanitizer:
    """
    Oyun metinlerindeki renk kodları, değişkenler ve format etiketlerini 
    korumak için maskeleme ve geri yükleme işlevleri sunar.
    """
    
    TAG_REGEX = re.compile(
        r'('
        r'<[^>]+>|'               # HTML/XML etiketleri
        r'\{[^{}]+\}|'            # Süslü parantez değişkenleri
        r'%[0-9]*\$?[a-zA-Z%]|'   # printf format belirteçleri
        r'\\n|\\r|\\t|'           # Kaçış dizileri (string içinde)
        r'[\n\r\t]'               # Doğrudan alt satır / tab karakterleri
        r')'
    )
    
    MASK_PATTERN = re.compile(r'__TAG_(\d+)__', re.IGNORECASE)
    TR_TO_SAFE = str.maketrans("çğışüöÇĞİŞÜÖ", "cgisuoCGISUO")

    @classmethod
    def mask_tags(cls, text: str) -> tuple[str, dict[str, str]]:
        if not text:
            return text, {}

        tag_map = {}
        tag_counter = 0

        def replace_match(match):
            nonlocal tag_counter
            tag = match.group(0)
            mask = f"__TAG_{tag_counter}__"
            tag_map[mask] = tag
            tag_counter += 1
            return mask

        masked_text = cls.TAG_REGEX.sub(replace_match, text)
        return masked_text, tag_map

    @classmethod
    def unmask_tags(cls, masked_text: str, tag_map: dict[str, str]) -> str:
        if not masked_text or not tag_map:
            return masked_text

        result = masked_text
        for mask, original_tag in tag_map.items():
            result = result.replace(mask, original_tag)

        def regex_restore(match):
            index = match.group(1)
            exact_key = f"__TAG_{index}__"
            return tag_map.get(exact_key, match.group(0))

        result = re.sub(r'__\s*TAG\s*_\s*(\d+)\s*__', regex_restore, result, flags=re.IGNORECASE)
        return result

    @classmethod
    def safe_font_convert(cls, text: str) -> str:
        """
        Türkçe karakter desteği olmayan oyun fontlarında kutucuk/bozulma olmaması için
        Türkçe harfleri güvenli karakterlere dönüştürür (ç->c, ş->s, ğ->g vb.).
        """
        if not text:
            return text
        return text.translate(cls.TR_TO_SAFE)


def mask_tags(text: str) -> tuple[str, dict[str, str]]:
    return TagSanitizer.mask_tags(text)


def unmask_tags(masked_text: str, tag_map: dict[str, str]) -> str:
    return TagSanitizer.unmask_tags(masked_text, tag_map)


def safe_font_convert(text: str) -> str:
    return TagSanitizer.safe_font_convert(text)
