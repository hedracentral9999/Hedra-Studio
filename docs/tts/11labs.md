Chèn ký hiệu đọc cho ElevenLabs V3.

Giữ nguyên câu chữ gốc. Chỉ chỉnh dấu câu rất nhẹ nếu cần cho nhịp đọc.

Nhiệm vụ:
Thêm audio tag, nhịp nghỉ và nhấn nhá để ElevenLabs V3 đọc tự nhiên hơn, có cảm xúc hơn và phù hợp hơn với ngữ cảnh của văn bản.

Chọn cảm xúc, cách đọc, nhịp và mức độ nhấn nhá theo đúng nội dung: bán hàng, kể chuyện, giáo dục, tin tức, review, hướng dẫn, quảng cáo, phỏng vấn, phim, audiobook, tài liệu chuyên môn hoặc bất kỳ thể loại nào khác.

Ưu tiên output dễ quan sát:
* Trình bày rõ ràng, thoáng, dễ đọc bằng mắt trước khi render.
* Mỗi ý chính hoặc lượt thoại nên nằm trên một đoạn riêng.
* Có thể để dòng trống giữa các đoạn để người dùng dễ kiểm tra trong Cursor.

Được phép thêm:

* audio tag trong dấu []
* inline tag khi trong cùng một câu hoặc cùng một lượt nói có chuyển cảm xúc
* dấu ... để ngắt nghỉ, do dự, kéo nhịp hoặc tạo khoảng lặng
* dấu — để khựng nhẹ hoặc chuyển nhịp nhanh
* xuống dòng để chia đoạn hợp lý
* VIẾT HOA từ quan trọng nếu thật sự cần nhấn mạnh

Không được:

* viết lại nội dung
* thêm ý mới
* bớt ý
* đổi ý nghĩa
* đổi vai nói
* đổi thứ tự hội thoại
* đổi tên riêng, thương hiệu, giá tiền, số liệu, thông số
* thêm tiêu đề
* thêm giải thích
* thêm markdown
* thêm chữ thừa trước hoặc sau kết quả

Cách xử lý phát âm và Việt hóa:

* Không Việt hóa thêm nếu từ gốc đã rõ và ElevenLabs có thể đọc được.
* Ưu tiên giữ nguyên tên riêng, thương hiệu, model máy, thuật ngữ kỹ thuật và tên nền tảng.
* Giữ nguyên các từ quen thuộc như: Samsung DeX, SamsungDex, shop, box, test, data, unlock, reset, TikTok, video, Snapdragon, Note 20 Ultra, S20 Plus.
* Không tự đổi Samsung DeX thành Sam-sung Đéc, shop thành sốp, box thành bóc, test thành tét, unlock thành ăn-lóc, reset thành ri-sét nếu input chưa viết như vậy.
* Nếu input đã được Việt hóa từ bước trước thì chỉ giữ lại khi nghe tự nhiên; nếu quá khó hiểu hoặc quá sai thương hiệu, được phép trả về dạng gốc dễ hiểu hơn.
* Chỉ chuẩn hóa số, tiền, phần trăm, ngày tháng, số điện thoại hoặc ký hiệu khó đọc khi thật sự cần cho TTS.
* Ví dụ nên làm: 880k → tám trăm tám mươi nghìn, A-Z → A tới Z.
* Ví dụ không nên làm: Samsung DeX → Sam-sung Đéc, shop → sốp, test → tét.

Cách dùng audio tag:

* Đặt tag ở đầu lượt nói hoặc đầu đoạn khi cần xác định cảm xúc chính.
* Dùng inline tag khi cảm xúc hoặc cách đọc đổi nhẹ ngay trong cùng một câu hoặc cùng một lượt nói.
* Đẩy cảm xúc rõ hơn bản gốc một mức, nhất là với hội thoại bán hàng, tư vấn, video ngắn, TikTok hoặc nội dung viral.
* Không tag mọi câu, nhưng đừng quá nhạt. Mỗi lượt thoại hoặc mỗi cụm ý quan trọng nên có tag cảm xúc nếu giúp giọng đọc sống động hơn.
* Không spam tag.
* Dùng tag hợp lý, vừa đủ, đúng chỗ, ưu tiên cảm xúc nghe được qua giọng nói.
* Một tag có thể áp dụng cho cả một đoạn ngắn nếu cảm xúc không đổi.
* Với nội dung nghiêm túc, chuyên môn hoặc tin tức, ưu tiên tag trung tính như [professional], [calmly], [serious], [thoughtful].
* Với nội dung giải trí, bán hàng hoặc hội thoại đời thường, ưu tiên tag cảm xúc giọng nói như [excited], [happy], [playful], [surprised], [impressed], [reassuring], [warmly].
* Hạn chế mạnh các tag cười như [laughs], [laughing], [chuckles], [giggles]. Chỉ dùng khi câu thật sự có hành động cười rõ ràng, hoặc cuối một đoạn rất hài.
* Không thêm [laughs] sau nhiều câu liên tiếp. Một kịch bản ngắn chỉ nên có tối đa 1-2 tag cười. Nếu input đã có quá nhiều [laughs], hãy lược bớt và thay bằng nhấn nhá chữ, kéo âm, dấu ... hoặc tag cảm xúc khác.
* Không dùng [laughs] như dấu chấm câu. Nếu chỉ muốn câu nghe vui hơn, dùng [playful], [excited], [warmly] hoặc nhấn mạnh từ khóa thay vì thêm cười.
* Ngoại lệ bắt buộc: nếu input đã viết rõ tiếng cười như `haha`, `hahaha`, `hahahahahaha`, `hehe`, `hehehe`, `hihi`, `kkkk`, `kkk`, thì phải chèn tag cười phù hợp **ngay trước chuỗi tiếng cười đó**.
* Thứ tự đúng: `[laughs] hahahahahahaha`, `[chuckles] hehehe`, `[giggles] hihihi`. Không đặt tag sau tiếng cười.
* Giữ nguyên chuỗi tiếng cười gốc, không xóa, không rút ngắn, không đổi số lần lặp. Chỉ thêm một tag ngay trước chuỗi đó.
* Mặc định dùng `[laughs]` cho `haha`, `hahaha`, `kkkk`, `kkk`; dùng `[chuckles]` cho tiếng cười nhẹ như `hehe`; dùng `[giggles]` cho tiếng cười khúc khích như `hihi` nếu hợp ngữ cảnh.
* Nếu chuỗi tiếng cười đã có tag cười ngay trước thì không thêm tag thứ hai.
* Khi có câu hỏi của khách, ưu tiên [curious], [thoughtful], [surprised] nếu phù hợp.
* Khi có câu trả lời/tư vấn của shop, ưu tiên [reassuring], [confident], [warmly], [excited] nếu phù hợp.
* Khi có cảnh báo, rủi ro, mất dữ liệu, giá trị quan trọng, ưu tiên [serious] hoặc [calmly].

Cách dùng pause:

* Dùng ... hợp lý, vừa đủ, đúng chỗ.
* Không thêm ... sau mọi câu.
* Không chèn ... quá dày.
* Ưu tiên giữ dấu câu gốc nếu câu đã có nhịp tự nhiên.
* Chỉ thêm ... khi cần ngập ngừng, chuyển cảm xúc, tạo khoảng lặng, hoặc nhấn trước ý quan trọng.
* Nếu input đã có ..., không cần thêm nhiều pause mới.

Cách dùng nhấn mạnh:

* Dùng VIẾT HOA hợp lý, vừa đủ, đúng chỗ.
* Chỉ viết HOA khi thật sự cần nhấn mạnh từ khóa quan trọng.
* Không viết HOA cả đoạn.
* Không lạm dụng nhấn mạnh.
* Ưu tiên nhấn vào từ bộc lộ cảm xúc, đánh giá, cao trào hoặc điểm bán/chốt ý: NGON, QUÁ NGON, XỨNG ĐÁNG, CHÂN ÁI, HỢP LÍ, KHÔNG SỢ NHẦM, VÔ ĐỐI, CẮM LÀ DÙNG.
* Không tự kéo dài chữ/nguyên âm ở bước 11labs. Việc kéo dài âm chỉ do prompt Viral xử lý trước đó.
* Nếu câu đang có tag cười nhưng ý chính là khen/ngạc nhiên/chốt vui, ưu tiên đổi sang nhấn bằng VIẾT HOA từ khóa:
  - Không tốt: [laughs] Cháo ngon lắm. [laughs]
  - Tốt hơn: [excited] Cháo ở đây QUÁ NGON nha các vợ.
  - Không tốt: Xứng đáng nha... [laughs]
  - Tốt hơn: Với tầm sáu mươi nghìn một tô thì quá là XỨNG ĐÁNG.

Cách chia đoạn:

* Bắt buộc chia đoạn vừa phải để ElevenLabs đọc có nhịp, không bị dồn hơi.
* Bắt buộc trình bày dễ quan sát trong file output.txt.
* Không để một đoạn quá dài. Mỗi đoạn nên khoảng 1 câu chính, hoặc tối đa khoảng 15-25 từ tiếng Việt nếu câu dài.
* Nếu một lượt nói dài hơn 2 câu, phải tách thành nhiều đoạn ngắn theo từng ý.
* Mỗi lượt thoại, mỗi câu hỏi, mỗi câu trả lời, mỗi ý chính nên đứng thành một đoạn riêng nếu làm giọng đọc rõ hơn.
* Khi gặp các điểm chuyển ý như: nhưng, còn nếu, sau đó, xong xuôi, vì vậy, thế thì, hoặc khi cảm xúc đổi rõ, nên xuống dòng.
* Với câu dài có nhiều vế, có thể chia bằng dấu chấm, dấu phẩy, dấu ... hoặc xuống dòng để tạo nhịp tự nhiên.
* Không tách vụn từng cụm quá ngắn nếu làm câu bị rời rạc.
* Không gộp nhiều lượt hội thoại vào cùng một đoạn.
* Nên để một dòng trống giữa các đoạn/lượt thoại để dễ kiểm tra thủ công.
* Nếu đoạn đã có tag ở đầu và cảm xúc không đổi, có thể giữ tag cho cả 1-2 câu ngắn; nếu sang ý mới hoặc cảm xúc mới thì xuống dòng và thêm tag mới nếu cần.
* Không cần thêm audio tag cho mỗi dòng mới. Xuống dòng chỉ để chia nhịp đọc và tách ý.
* Chỉ thêm tag mới khi cảm xúc, vai nói, mức độ nhấn mạnh hoặc cách đọc thay đổi rõ.
* Nếu nhiều dòng liên tiếp vẫn cùng một cảm xúc, dùng một tag ở đầu cụm là đủ.

Audio tag có thể dùng:
[happy], [excited], [surprised], [curious], [thoughtful], [confident], [reassuring], [warmly], [serious], [playful], [sarcastic], [affirmative], [impressed], [softly], [calmly], [dramatically], [quickly], [slowly], [professionally], [professional]

Tag phi ngôn ngữ (non-verbal):
[laughs], [laughing], [chuckles], [giggles], [wheezing], [snorts], [crying], [sighs], [exhales], [exhales sharply], [inhales deeply], [whispers], [shouts], [singing], [woo], [clears throat], [short pause], [long pause]

Khi input có âm thanh phi ngôn ngữ viết thành chữ, phải chèn tag phù hợp **ngay trước** chuỗi âm thanh đó. Giữ nguyên chuỗi gốc, không xóa, không rút ngắn, không đổi số lần lặp. Chỉ thêm một tag, không thêm tag thứ hai nếu đã có tag trước chuỗi đó.

### Quy tắc mapping âm thanh → tag

**Nhóm cười — Ưu tiên nhẹ nhàng, không lạm dụng:**
| Writing pattern | Tag | Ghi chú |
|----------------|-----|---------|
| `haha`, `hahaha`, `hahahahaha`... (từ 2 lần trở lên) | `[laughs]` | Cười to, dài |
| `hahaha` chuỗi rất dài (≥ 8 âm) | `[laughing]` | Cười liên tục, không ngắt |
| `hehe`, `hehehe`... | `[chuckles]` | Cười nhẹ, cười khẽ |
| `hihi`, `hihihi`... | `[giggles]` | Cười khúc khích |
| `hì hì`, `hí hí` | `[giggles]` hoặc `[chuckles]` | Cười nhẹ tiếng Việt |
| `kkk`, `kkkk`, `kkkkkk`... | `[laughs]` | Cười viết tắt |
| `*cười*`, `*cười lớn*`, `*cười phá lên*` | `[laughs]` | Mô tả cười trong dấu * |

**Nhóm thở — Chỉ dùng khi có writing pattern rõ, không tự suy diễn:**
| Writing pattern | Tag |
|----------------|-----|
| `*thở dài*`, `*sigh*`, `*phào*`, `*phì*` | `[sighs]` |
| `*thở ra*`, `*xả hơi*`, `*phào nhẹ*`, `*thở phào*` | `[exhales]` |
| `*thở mạnh*`, `*hắt ra*`, `*phụt*`, `*thở hắt*` | `[exhales sharply]` |
| `*hít sâu*`, `*hít một hơi*`, `*hít vào*`, `*hít mạnh*` | `[inhales deeply]` |

**Nhóm giọng nói đặc biệt:**
| Writing pattern | Tag |
|----------------|-----|
| `*nói thầm*`, `*thì thầm*`, `*rì rầm*`, `*psst*`, `*suỵt*`, `*nói nhỏ*` | `[whispers]` |
| `*hét*`, `*gào*`, `*la lớn*`, `*hét to*`, `*quát*`, `*gào lên*` | `[shouts]` |
| `*hát*`, `*ca hát*`, `*ngân nga*`, `la la la`, `lá la la` | `[singing]` |

**Nhóm cảm xúc mạnh:**
| Writing pattern | Tag |
|----------------|-----|
| `*khóc*`, `*nức nở*`, `*thổn thức*`, `*sụt sùi*`, `hu hu`, `huhu`, `*hu hu*` | `[crying]` |
| `*woo*`, `*hú*`, `*hú hú*`, `*hu*`, `*u u*` | `[woo]` |

**Nhóm âm thanh khác:**
| Writing pattern | Tag |
|----------------|-----|
| `*hắng giọng*`, `*e hèm*`, `*ahem*`, `*khụ khụ*` | `[clears throat]` |
| `*khịt mũi*`, `*hừ*`, `*phì cười*`, `*hừ hừ*` | `[snorts]` |
| `*thở khò khè*`, `*sặc*`, `*cười sặc sụa*`, `*thở dốc*` | `[wheezing]` |

**Nhóm pause — Chỉ dùng khi writing pattern tường minh:**
| Writing pattern | Tag |
|----------------|-----|
| `*tạm dừng*`, `*ngập ngừng*`, `*im*`, `*silence*` | `[short pause]` |
| `*im lặng*`, `*dừng lâu*`, `*ngừng một lát*`, `*khoảng lặng*` | `[long pause]` |

### Nguyên tắc chung

* Chỉ map khi writing pattern XUẤT HIỆN RÕ RÀNG trong input. Không tự suy diễn cảm xúc từ nội dung.
* Giữ nguyên chuỗi gốc, không đổi chính tả, không bỏ dấu `*`, không đổi độ dài.
* Không thêm tag thứ hai nếu đã có tag phi ngôn ngữ ngay trước chuỗi đó.
* Nếu một chuỗi khớp nhiều pattern, ưu tiên pattern cụ thể nhất.
* Kết hợp được: tag cảm xúc + tag phi ngôn ngữ. Ví dụ: `[curious] [sighs] ...` hoặc `[excited] [woo] Có LUÔN nha!`
* Không tự thêm tag phi ngôn ngữ khi không có writing pattern tương ứng trong input.

Chỉ trả về văn bản đã chèn ký hiệu đọc cho ElevenLabs V3.

Nhấn mạnh:
- Có thể VIẾT HOA một số từ/cụm từ thật sự quan trọng để tạo lực nhấn khi đọc.
- Chỉ viết hoa rất ít, tối đa 1-3 cụm trong một đoạn ngắn.
- Ưu tiên viết hoa các từ bán hàng hoặc cảm xúc như: QUÁ NGON, VÔ ĐỐI, CHỈ, CẮM LÀ DÙNG, NGON ĐÉT.
- Với nội dung review/đời thường, ưu tiên nhấn cảm xúc tự nhiên kiểu: QUÁ NGON, SẠCH SẼ, CHÂN ÁI, XỨNG ĐÁNG, HỢP LÍ, KHÔNG SỢ NHẦM.
- Không tự kéo dài âm trong bước 11labs. Nếu input đã có chữ kéo dài từ bước Viral thì giữ nguyên khi hợp lý, nhưng không tạo thêm chữ kéo dài mới.
- Không thay cảm xúc bằng quá nhiều [laughs]. Tag cười chỉ là gia vị, không phải cách nhấn chính.
- Không dùng Markdown in đậm như **chữ**, vì ElevenLabs có thể đọc ký tự hoặc làm text đầu vào bị bẩn.
- Không viết hoa cả câu dài, tránh làm giọng đọc bị gắt hoặc thiếu tự nhiên.
