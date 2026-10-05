import re

class TagSanitizer:
    """
    Oyun metinlerindeki renk kodları, değişkenler ve format etiketlerini 
    korumak için maskeleme ve geri yükleme işlevleri sunar.
    """
    
    # Oyun etiketleri için kapsamlı Regex deseni:
    # 1. <...> tarzı XML/HTML etiketleri (<COLOR ff0000>, </COLOR>, <ICON ...>)
    # 2. {...} tarzı değişkenler ({PlayerName}, {0}, {ITEM_ID})
    # 3. %s, %d, %1$s, %f tarzı printf format belirteçleri
    # 4. \n, \r, \t kaçış karakterleri
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

    @classmethod
    def mask_tags(cls, text: str) -> tuple[str, dict[str, str]]:
        """
        Metin içerisindeki etiketleri yakalayıp yerlerine geçici maskeler koyar.
        
        Returns:
            (masked_text, tag_map)
        """
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
        """
        Çeviriden gelen metindeki maskelerin yerine orijinal etiketleri geri koyar.
        LLM tarafında oluşabilecek boşluk veya harf büyüklüğü sapmalarını da tolere eder.
        """
        if not masked_text or not tag_map:
            return masked_text

        # Önce birebir maskeleri değiştir
        result = masked_text
        for mask, original_tag in tag_map.items():
            result = result.replace(mask, original_tag)

        # Eğer LLM maskeyi büyük/küçük harf veya etrafına esnek boşluk koyarak bozduysa (örn: __tag_0__, __TAG_ 0__)
        def regex_restore(match):
            index = match.group(1)
            exact_key = f"__TAG_{index}__"
            return tag_map.get(exact_key, match.group(0))

        # Esnek yakalama için regex
        result = re.sub(r'__\s*TAG\s*_\s*(\d+)\s*__', regex_restore, result, flags=re.IGNORECASE)

        return result


def mask_tags(text: str) -> tuple[str, dict[str, str]]:
    return TagSanitizer.mask_tags(text)


def unmask_tags(masked_text: str, tag_map: dict[str, str]) -> str:
    return TagSanitizer.unmask_tags(masked_text, tag_map)
