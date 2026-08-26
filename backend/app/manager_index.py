import hashlib,re

# Surname initials cover the common Chinese surnames seen in fund-management datasets.
SURNAME_INITIAL={}
def add(initial,chars):
    for c in chars:SURNAME_INITIAL[c]=initial
add('A','安敖艾')
add('B','白鲍毕卞边柏班暴贝卜步包')
add('C','陈程崔蔡曹常柴车成迟楚褚昌巢')
add('D','丁董杜戴邓窦刁段狄党单')
add('F','方范冯傅费符封房丰樊')
add('G','高郭顾龚葛耿关管古甘宫谷盖')
add('H','黄何胡韩侯郝贺霍洪杭华花')
add('J','金姜蒋江季贾纪焦吉简景靳井')
add('K','孔康柯阚寇匡蒯')
add('L','李刘林梁罗卢吕陆廖赖雷黎龙凌柳骆蓝劳娄连练')
add('M','马孟毛苗莫梅米明穆麦蒙')
add('N','倪宁牛聂农南钮')
add('O','欧区')
add('P','潘彭裴蒲庞皮平浦')
add('Q','钱秦邱丘乔齐祁屈强全戚')
add('R','任饶阮容')
add('S','孙沈石史施邵宋苏舒盛时时司桑商申尚隋水沙')
add('T','谭唐陶田童汤涂滕屠覃佟')
add('W','王吴魏汪文万韦温伍巫武翁危闻')
add('X','徐谢许萧肖夏熊薛向项席辛邢习奚解')
add('Y','杨叶于余袁姚严颜俞尹易殷喻尤岳应虞俞燕游')
add('Z','张赵周朱郑钟曾邹庄章詹祝左宗翟甄卓祖')

def surname_initial(name):
    s=str(name or '').strip()
    if not s:return '#'
    if re.match(r'[A-Za-z]',s):return s[0].upper()
    return SURNAME_INITIAL.get(s[0],'#')

def manager_id(name,company):
    return hashlib.sha1(f'{name}|{company}'.encode('utf-8')).hexdigest()[:16]
