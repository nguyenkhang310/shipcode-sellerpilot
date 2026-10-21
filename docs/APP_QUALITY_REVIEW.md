# Rà soát app sau khi hợp nhất nhánh Hoàng

## Đăng nhập, Face ID và giao diện — 21/10/2026

- App đăng nhập bằng tài khoản thành viên Kênh Người Bán local. Token opaque
  ngẫu nhiên, hash trong database, hết hạn 7 ngày; đăng xuất thu hồi, thay mật
  khẩu/quyền quản lý làm phiên cũ không còn dùng được. Route chat, số liệu,
  chỉnh sản phẩm/đơn, proposal và ảnh bản nháp yêu cầu phiên. Health công khai.
- Chặn ảnh chưa đăng tại cả static API và static Flask; ảnh sản phẩm đã đăng
  vẫn công khai. Private image ở app/web gửi Bearer đúng origin, không lưu
  token trong Web Storage. Proposal giá kiểm tra đúng sản phẩm/shop trước cả
  nhánh trả kết quả lặp để không lộ hoặc từ chối nhầm proposal ngoài phạm vi.
- Face ID dùng SecureStore/Keychain với yêu cầu sinh trắc học; phiên thường
  được xóa khi bật. Khóa khi xuống nền, che app switcher, có mật khẩu dự phòng,
  xử lý khóa Keychain mất hiệu lực và ghi đồng thời. Expo Go/web không hiện
  nút mở khóa sinh trắc học khi chưa hỗ trợ hoặc chưa được người dùng bật.
- Login dùng logo ShipCode xóa phông do người dùng cung cấp, cân lại logo/form
  trên mobile/desktop, viền/chữ riêng cho sáng/tối, tắt vòng chuyển động theo
  Reduce Motion và dọn animation khi unmount. Bỏ regex email/điện thoại sai với
  contract tài khoản: `utech` đăng nhập bình thường. Trợ giúp, hiện mật khẩu,
  trạng thái lỗi và submit đều hoạt động thực tế.
- Thêm `npm run auth:reset`: nhập mật khẩu trực tiếp trong terminal, chỉ đổi
  hash của owner shop local; kiểm tra lại token cũ bị từ chối và dữ liệu giữ
  nguyên trên shop tạm. Không sửa mật khẩu shop thật trong quá trình kiểm tra.
- 682 test backend qua; 19 test marketplace, 11 test adapter xác thực/Keychain,
  12 test transport/message, 21 test extension và test SVG qua. Migration chạy
  sạch rồi downgrade/re-upgrade trên database tạm. Typecheck và export web/iOS
  qua. Browser QA kiểm tra login cả sáng/tối ở 320/390/430/1024px, đăng nhập sai,
  ảnh riêng tư, thu hồi và hết hạn; hồi quy 5 tab, chat retry/upload, xử lý đơn.

Chưa xác thực Face ID bằng camera iPhone thật. Mac hiện chỉ có Command Line
Tools, chưa có Xcode đầy đủ; đã kiểm tra cấu hình native chứa quyền Face ID,
không coi export iOS là cài bản native. Quy trình cài, tài khoản, phiên và phạm
vi triển khai: [AUTHENTICATION.md](AUTHENTICATION.md).

## Đồng bộ đơn, vận chuyển và trợ lý — 21/10/2026

- App, web người bán/người mua và script tạo đơn dùng chung nhật ký SQLite.
  Trigger ghi trạng thái trong cùng transaction; retry từ app gắn lên đúng
  sự kiện, không nhân đôi. Xóa đơn dọn dữ liệu phụ để ID được dùng lại không
  mang lịch sử/vận đơn cũ. Đơn cũ thiếu mốc hiện trạng thái đúng cùng thông báo
  chưa có thời điểm; dữ liệu nhập ở trạng thái đã xử lý chỉ ghi nhận ban đầu.
- Kênh quản trị dùng cùng luật chuyển trạng thái với app/seller; callback thanh
  toán đến muộn không kéo đơn đã giao về chờ lấy hàng. COD giả lập chưa giao
  không tự được ghi nhận đã thu tiền chỉ vì xác nhận/bàn giao.
- Vận đơn có bộ chọn hãng và mã nhập tay, review/xác nhận ở app, sao chép bằng
  Clipboard; web cũng sửa trước bàn giao, so sánh giá trị cũ trong transaction.
  Chi tiết web người mua và app đọc cùng vận đơn. Không phát hành mã hãng giả,
  không tự dựng vị trí bưu kiện/ETA. Giao diện ghi rõ ngày đặt ở header.
- Chat đọc lại đơn từ server, hiểu mã đơn/câu hỏi tiếp/bổ sung mã sau câu hỏi
  làm rõ, đối chiếu tối đa 5 mã và không lộ đơn khác shop. Có nút mở xử lý ngay
  trong chat; yêu cầu hủy bằng lời chưa thực thi. Câu đọc đơn không gọi model;
  câu tư vấn theo đơn có chi tiết mới nhất và một lần sinh câu trả lời.
- `npm run demo` dừng sớm nếu API và web được cấu hình hai database khác nhau.
  Cấu hình hiện tại đã qua kiểm tra cùng nguồn. Đối chiếu chỉ đọc trên shop
  hiện tại: 0 đơn thiếu dòng hàng, 0 lệch tổng tiền, 0 lệch tổng tồn/phân loại,
  0 sản phẩm tồn âm. Không ghi hoặc sửa đơn shop trong quá trình audit.
- 659 test backend và 19 test luồng marketplace qua; ca xuyên app ↔ web ↔
  người mua đối chiếu trạng thái, vận đơn, số đã bán, tồn và thống kê 1/7/30 ngày.
  Typecheck, build web/iOS, 12 test transport/message qua. Browser QA xác minh
  chọn hãng, copy mã, review, bàn phím, retry/409 và đơn cũ ở 320–520px.
- AI thật qua `ai:check` (chat Việt, tiền Việt, chi phí, ảnh tự vẽ và tham chiếu
  ngắn). Benchmark shop tạm: đọc đơn giản 6–28ms, tư vấn 2,39s, tính lời 1,71s,
  đọc ảnh/soạn nháp 1,59s; tám ca qua và không fallback. Không coi đây là SLA.
- Thêm `expo-clipboard` đúng dải Expo 57. Cập nhật riêng `shell-quote` trong dải
  tương thích để loại cảnh báo critical. Npm audit còn 24 cảnh báo ở cây phụ
  thuộc hiện tại (7 moderate, 17 high); chưa nâng breaking Expo/React Native.

Phạm vi: đồng bộ gian hàng local, chưa có Shopee Open Platform hay API hãng vận
chuyển. Mã vận đơn cần do shop nhập từ phiếu giao thật. Không reset dữ liệu hoặc
thay `.env`. Chưa kiểm tra lại Clipboard, bàn phím và safe area trên điện thoại
thật; các bài browser dùng shop tạm riêng và không mở popup.

## Xem từng ngày và sửa thủ công trong app — 21/10/2026

- Dashboard nhận `date=YYYY-MM-DD`, ngày lịch sử đủ 24 giờ Việt Nam, hôm nay chỉ
  đến hiện tại; so sánh cùng thời lượng ngày trước. Kiểm tra ranh giới 17:00 UTC,
  ngày rỗng, năm nhuận, ngày tương lai, tổng series và trạng thái đơn bằng fixture.
- Bộ chọn kỳ trượt 210ms, không animate lại khi xoay màn hình, tắt chuyển động
  theo tùy chọn hệ thống. Lịch cuộn được ở màn hình thấp, nút xem luôn ở cuối;
  hỗ trợ chuyển ngày trước/sau. Cache tách từng ngày, hủy/loại phản hồi muộn,
  không gắn số ngày cũ lên ngày mới, không lẫn lựa chọn mốc biểu đồ giữa hai ngày.
- Form sửa sản phẩm ở ngay app: tên/mô tả/giá/tồn, phân loại cụ thể, review,
  xác nhận bỏ thay đổi, retry giữ UUID và tải lại khi 409. Backend scope seller,
  version toàn sản phẩm/phân loại, transaction và receipt trong shop; cập nhật
  giá thấp nhất/tổng tồn từ phân loại khả dụng. Chỉ validate trường đang sửa;
  không tự đánh dấu thay đổi vì khoảng trắng trong nội dung cũ.
- Đồng bộ tiêu đề, nhịp khoảng cách và màu chọn giữa các tab; nút thẻ sản phẩm
  gọn trên màn hình 320px, metadata xuống dòng thay vì đẩy badge ra ngoài. Ô
  nhập dài giới hạn chiều cao, cuộn nội bộ; footer lưu nằm ngoài vùng cuộn.
- Modal sản phẩm và đơn hàng theo VisualViewport riêng trên web (không chỉ root
  app), nên footer vẫn nhìn thấy khi bàn phím bật. Native tiếp tục dùng
  KeyboardAvoidingView. Vùng cuộn đưa ô đang nhập lên trên footer khi focus hoặc
  bàn phím làm co màn hình; bước review trở lại đầu nội dung. Test web kiểm tra
  cả nút lưu và toàn bộ ô đang nhập nằm trong vùng nhìn thấy.
- 631 test backend, 4 test state dashboard, 12 test transport/message, native SVG
  parser và 21 test extension qua. Browser audit năm tab, đổi kỳ, đổi theme,
  chat motion và form sửa dùng shop QA tạm; không gọi/sửa shop người dùng.

Phạm vi: sửa thủ công hỗ trợ gian hàng local, không thay quyền Open API Shopee.
Ảnh/SKU/ngành hàng/trạng thái sản phẩm chưa thuộc form sửa này. Chưa kiểm tra lại
bàn phím, Dynamic Type, safe area và hiệu ứng trên thiết bị iPhone/Android thật.

## Xử lý và theo dõi đơn trong app — 21/10/2026

- Mỗi thẻ đơn có nút Theo dõi và Xử lý đơn. Bottom sheet tách tiến trình,
  vận đơn, lịch sử khỏi thông tin nhận hàng và form xử lý; không mở trang mua
  hàng hoặc tab mới. Bộ lọc có số đơn theo trạng thái và từ khóa hiện tại.
- Chuyển trạng thái đi qua bước xem lại. Nhật ký, thông tin vận chuyển, kho và
  biên nhận lưu cùng giao dịch; thử lại cùng operation ID không thêm sự kiện
  hay hoàn kho lần hai. Phiên cũ bị từ chối bằng version/409.
- Chi tiết tự cập nhật mỗi 8 giây khi đang xem và chưa sửa; danh sách cập nhật
  10 giây khi ở đầu trang đầu tiên. Dừng đồng bộ form khi có nội dung chưa lưu,
  review hoặc đang gửi. Đóng form có thay đổi phải chọn tiếp tục hoặc bỏ.
- Theo dõi có hiệu ứng xuất hiện ngắn, phản hồi thành công sau khi server lưu;
  tôn trọng Giảm chuyển động. Kiểm tra sáng/tối và chiều rộng 320/390/520px.
- 642 test backend, 12 test transport/message và native SVG parser qua.
  Typecheck, build web, export iOS qua. Browser kiểm tra năm tab, form đơn,
  bàn phím giả lập, xác nhận → vận đơn → bàn giao → hoàn tất, cập nhật từ phiên
  khác, giữ nội dung đang nhập và xử lý xung đột; không phát sinh popup/page mới.

Phạm vi hiện tại là gian hàng local. Mã vận đơn do shop nhập, trạng thái do shop
cập nhật; chưa kết nối hãng vận chuyển để lấy các lần quét kiện hàng, GPS hoặc
ETA. Không tạo mốc thời gian cho trạng thái cũ/cập nhật ngoài app chưa có nhật ký.
Kiểm thử dùng shop tạm, chưa xác minh lại trên iPhone/Android thật.

## Cập nhật 21/10/2026

- Sửa cảnh báo native SVG `".55" is not a valid number or percentage string`:
  offset của viền kính chuyển sang `{0.55}`; trục gradient và opacity biểu đồ
  dùng giá trị số. Trước đó native đọc offset không hợp lệ thành 0, làm sai
  gradient; không chỉ là log thừa. `npm run test:svg` chạy extractor native thật
  và xác minh không cảnh báo, không dùng LogBox để che lỗi.

- Hiệu quả kinh doanh tách thành `PerformanceOverview`: tổng giá trị có khoảng
  thở riêng, hàng chỉ số chia bằng đường mảnh, biểu đồ và giá trị đã giao/hủy ở
  khung riêng. Bỏ nền navy nguyên khối. Cam logo dùng cho kỳ đang chọn, đường
  biểu đồ, điểm nhấn ưu tiên, lời mời phân tích và tab đang chọn; nền lớn trung tính.
- Thêm khu vực ưu tiên có hành động dẫn đúng danh sách lọc; phân bố đơn dùng
  thanh ngang và số lượng/tỷ lệ. Không bịa tăng trưởng khi thiếu kỳ so sánh.
- Kính dùng recipe sáng/tối riêng: frost 80%, viền trung tính tương phản, backdrop
  blur một lớp. Native dùng GlassView regular với colorScheme rõ; material/mask
  cập nhật theo theme. Lựa chọn theme lưu tuần tự và không bị hydration cũ ghi đè.
- Hệ icon điều hướng/lối tắt dùng chung SVG 24px, nét 1,65, không đổi thành mảng
  tô đậm khi chọn. Bỏ biểu tượng lấp lánh, tia sét và nhịp sóng trang trí. Cùng bộ
  icon được dùng ở extension; các nút thao tác cơ bản vẫn dùng glyph nền tảng.
- Gemini mặc định 60 giây, dùng deadline chung xuyên các bước trong một lượt.
  Quy tắc đọc số liệu Việt không dấu/có dấu bỏ gọi model với câu đơn giản;
  câu tính lời đơn giản chỉ gọi trích dữ kiện, kiểm tra rồi tính bằng Decimal.
- Đo API thật trên shop tạm: năm ca đơn giản 5–30ms không gọi AI, tư vấn 32,9s,
  tính lời 20,5s/một lần gọi, ảnh 16,5s. Cả tám ca qua, không fallback. Provider
  vẫn biến động; đây không phải cam kết hết timeout. Report gitignore tại
  `docs/evaluations/ai-latency/results.json`; chạy lại bằng `npm run ai:benchmark`.
- 600 test backend đã qua. Các mục phía dưới ghi lại lần kiểm tra trước và
  cấu hình 45 giây cũ; cấu hình hiện tại xem `GEMINI_API_SETUP.md`.
- Bản cuối qua typecheck, 12 test transport/message, 21 test extension; browser
  audit năm tab, đổi kỳ chậm/lỗi/phản hồi muộn, readability và 16 lần chuyển
  sáng/tối đều qua. Theme vẫn đúng sau reload, bản nháp chat giữ nguyên. Các test
  browser đo cả bố cục ở 320–520px; ảnh/result nằm trong thư mục evaluations.

Giới hạn: chưa kiểm tra lại trên iPhone thật (bàn phím, safe area, Dynamic Type
và GlassView iOS 26). Browser fixture dùng dữ liệu tạm, không can thiệp tài khoản
Shopee/TikTok hoặc API đang phục vụ người dùng.

Đã lưu các thay đổi trước đó trong `e355cf4`, rồi hợp nhất `origin/hoangbadu`
(commit `46b2c5a`) vào `main` bằng merge `6ca7190`. Không ghi đè `.env` hoặc push lên remote trong lượt này.

## Giao diện

- Căn phần biểu tượng tròn trong ảnh HCMUTE, loại khoảng trắng/chữ bên dưới khỏi khung avatar bằng layout, giữ nguyên file gốc.
- Thanh dưới có đường khoét cong thật theo kích thước màn hình, nút SellerPilot 72px nhô lên 28px; vùng chọn cũng theo mask để không đè lên đường cong. Khoảng đệm nội dung/composer dùng chung một công thức, giữ vùng chạm phần nhô lên. Native dùng mask + material, web dùng CSS clip-path, đặt backdrop blur ngay trên phần tử mask và bỏ filter ở cha để kính không xuyên chữ sắc nét; hỗ trợ Giảm độ trong suốt.
- Tăng chữ nội dung và chữ phụ, độ tương phản; giữ nhãn điều hướng ở 12px, vùng bấm rõ, icon outline khi chưa chọn và navy khi chọn.
- Thẻ sản phẩm/đơn có thứ bậc rõ hơn, trạng thái màu nhẹ, nút thêm sản phẩm nổi bật, hành động phụ gọn hơn. Ảnh không bị co ngang vì tiêu đề dài.
- Thẻ bản nháp có gallery bấm đổi ảnh, ảnh chính contain và mở rộng mô tả; thêm hủy bản nháp đang thu thập. Không hiện tồn `null` hoặc tải URL ảnh rỗng.
- Chặn phản hồi tải lịch sử sau thao tác đăng/điền form ghi đè lên hội thoại mới.
- Các bài kiểm tra bố cục dùng dữ liệu giả; không gọi shop đang sử dụng hoặc gửi ảnh cá nhân lên AI.

## AI và dữ liệu

- Khi sửa lựa chọn sản phẩm bằng câu như “không, xe đó”, cập nhật ngành hàng cùng tiêu đề/mô tả thay vì giữ ngành cũ.
- Đọc số tồn viết bằng chữ, số có phân cách hàng nghìn, “hết hàng”; không đọc tiền, số lẻ hoặc khoảng số thành tồn kho.
- Luồng local và browser dùng chung kiểm tra vai trò số tiền, chặn giá vốn bị dùng làm giá bán.
- Tin nhắn thuộc tính trên TikTok chỉ cập nhật bản nháp; không ghi form khi chat. Bỏ các số mặc định và thuộc tính tự chọn; giữ tồn 0, không thêm tuyên bố chính hãng.
- Kiểm tra giá trị thực sự được giữ trong ô trước khi báo điền xong; giữ nhãn “chưa đăng”.
- Khi Groq đang trong cooldown do 429, không rút ngắn deadline Gemini để chuyển sang một backup đã biết không sẵn sàng.

## Phạm vi xác minh

Các bài backend, transport, fixture Chrome và build web/iOS được ghi kết quả ở terminal.
Ảnh/JSON QA nằm trong `docs/evaluations/` và được gitignore. Hướng dẫn chạy nằm ở
`frontend/tests/README.md` và `extensions/shopee-connector/README.md`.

Kiểm tra AI thật ban đầu gặp timeout Gemini rồi Groq trả 429. Phép đo độc lập cho
thấy TLS khoảng 0,23s, một yêu cầu rất ngắn nhận HTTP 200 sau 16,52s; một lượt prompt
chat đầy đủ chạm 45s. Sửa cutoff cứng 15s thành phần ngân sách còn lại sau khi dành
tối đa 20s cho backup; giữ tổng deadline bằng timeout wall-clock cho cả primary/backup, connect/pool 5s, write 10s. Log tách pha
network timeout và ghi stage/elapsed khi fallback, không ghi key/prompt.

Lần `npm run ai:check` sau sửa **đã qua toàn bộ** trong 115,0s cho nhiều yêu cầu:
trích giá 5 xị, chat Việt, chi phí/phí/giá bán, đọc ảnh bàn phím tự vẽ và câu ngắn
“bàn phím đó”. Có lượt Gemini chạm read timeout khoảng 25s rồi **Groq trả lời thành
công**; đây là kiểm chứng tích hợp Gemini + backup, không phải bằng chứng mọi lượt
Gemini đều nhanh hoặc hết timeout/quota. Không tạo project ID giả hoặc xoay key
cùng project để vượt quota.

560 test backend, 12 test transport/message, 21 test extension đã qua. Bố cục
320–520px, lịch sử, input dài/cuộn, đổi kỳ và lỗi mạng được kiểm tra bằng fixture;
build web/iOS đã qua. Ảnh thật/tài khoản Shopee/TikTok đăng nhập và bàn phím/safe
area/Dynamic Type trên iPhone thật chưa được xác minh lại trong lượt này.
