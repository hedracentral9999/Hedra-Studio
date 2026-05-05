# ELEVENLABS — TEXT NORMALIZATION
# File: 03-el-normalization.md
# Nguồn: https://elevenlabs.io/docs/overview/capabilities/text-to-speech/best-practices

---

## 1. Tổng Quan

```
Normalization BẬT MẶC ĐỊNH cho tất cả TTS models.
Xử lý tự động: số điện thoại, tiền tệ, ngày tháng, địa chỉ, URL, viết tắt.

VẤN ĐỀ THEO MODEL:
  Flash v2.5:      "$1,000,000" → "one thousand thousand dollars" ❌
  Multilingual v2: "$1,000,000" → "one million dollars"          ✅

→ Dùng Multilingual v2 khi cần đọc số/tiền chính xác
```

---

## 2. Các Trường Hợp Hay Gặp Lỗi

| Input | Đọc sai | Cần convert thành |
|-------|---------|-------------------|
| `123-456-7890` | "một hai ba..." | "one two three, four five six..." |
| `$47,345.67` | sai format | "forty-seven thousand three hundred forty-five dollars and sixty-seven cents" |
| `2024-01-01` | tùy model | "January first, two-thousand twenty-four" |
| `9:23 AM` | có thể sai | "nine twenty-three AM" |
| `123 Main St` | tùy model | "one two three Main Street" |
| `example.com/link` | tùy model | "example dot com slash link" |
| `TB`, `km`, `%` | viết tắt | "terabytes", "kilometers", "percent" |
| `Ctrl + Z` | tùy model | "control z" |

---

## 3. Giải Pháp 1 — LLM Prompt Normalization (Recommended)

```
Chạy text qua LLM trước khi gửi sang TTS với prompt:

"Convert the output text into a format suitable for text-to-speech.
 Expand all abbreviations to full spoken forms. Convert:

 $42.50       → forty-two dollars and fifty cents
 £1,001.32    → one thousand and one pounds and thirty-two pence
 1234         → one thousand two hundred thirty-four
 3.14         → three point one four
 555-555-5555 → five five five, five five five, five five five five
 2nd          → second
 XIV          → fourteen (hoặc 'the fourteenth' nếu là title)
 3.5          → three point five
 ⅔            → two-thirds
 Dr.          → Doctor
 Ave.         → Avenue
 St.          → Street (ngoại trừ tên riêng: St. Patrick)
 Ctrl + Z     → control z
 100km        → one hundred kilometers
 100%         → one hundred percent
 elevenlabs.io/docs → eleven labs dot io slash docs
 2024-01-01   → January first, two-thousand twenty-four
 123 Main St, Anytown, USA → one two three Main Street, Anytown, United States of America
 14:30        → two thirty PM
 01/02/2023   → January second, two-thousand twenty-three (tùy locale)"
```

---

## 4. Giải Pháp 2 — Regex Preprocessing (Python)

```python
# pip install inflect
import inflect
import re

p = inflect.engine()

def normalize_text(text: str) -> str:
    def money_replacer(match):
        currency_map = {"$": "dollars", "£": "pounds", "€": "euros", "¥": "yen"}
        symbol, num = match.groups()
        num_clean = num.replace(',', '')
        if '.' in num_clean:
            dollars, cents = num_clean.split('.')
            return (f"{p.number_to_words(int(dollars))} "
                    f"{currency_map.get(symbol, 'currency')} and "
                    f"{p.number_to_words(int(cents))} cents")
        return f"{p.number_to_words(int(num_clean))} {currency_map.get(symbol, 'currency')}"

    text = re.sub(r"([$£€¥])(\d+(?:,\d{3})*(?:\.\d{2})?)", money_replacer, text)

    def phone_replacer(match):
        return ", ".join(
            " ".join(p.number_to_words(int(d)) for d in g)
            for g in match.groups()
        )
    text = re.sub(r"(\d{3})-(\d{3})-(\d{4})", phone_replacer, text)
    return text

# Ví dụ:
normalize_text("$1,234.56")    # → "one thousand two hundred thirty-four dollars and fifty-six cents"
normalize_text("555-555-5555") # → "five five five, five five five, five five five five"
normalize_text("£1000")        # → "one thousand pounds"
```

---

## 5. Giải Pháp 3 — Regex Preprocessing (TypeScript)

```typescript
// npm install number-to-words
import { toWords } from 'number-to-words';

function normalizeText(text: string): string {
  return text
    // Tiền tệ: $1,234.56 → "one thousand two hundred thirty-four dollars and fifty-six cents"
    .replace(/([$£€¥])(\d+(?:,\d{3})*(?:\.\d{2})?)/g, (_, currency, num) => {
      const currencyMap: Record<string, string> = {
        $: 'dollars', '£': 'pounds', '€': 'euros', '¥': 'yen'
      };
      const clean = num.replace(/,/g, '');
      if (clean.includes('.')) {
        const [dollars, cents] = clean.split('.');
        return `${toWords(+dollars)} ${currencyMap[currency]} and ${toWords(+cents)} cents`;
      }
      return `${toWords(+clean)} ${currencyMap[currency]}`;
    })
    // Số điện thoại: 555-555-5555 → "five five five, five five five, five five five five"
    .replace(/(\d{3})-(\d{3})-(\d{4})/g, (_, p1, p2, p3) =>
      [p1, p2, p3]
        .map((g: string) => g.split('').map((d: string) => toWords(+d)).join(' '))
        .join(', ')
    );
}

// Ví dụ:
normalizeText('$1,234.56');   // → "one thousand two hundred thirty-four dollars and fifty-six cents"
normalizeText('555-555-5555'); // → "five five five, five five five, five five five five"
```
