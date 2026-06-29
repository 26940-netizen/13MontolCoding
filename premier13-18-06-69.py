print("โปรแกรมคำนวณคะแนนรวม\n")
Eng =  int(input("คะแนนสอบอังกฤษ "))
Math = int(input("คะแนนสอบคณิตศาสตร์ฺ "))
Thai = int(input("คะแนนสอบไทย "))
total = Eng + Math + Thai
Avg = total/3

if Avg < 60:
    print("ผลคะแนนรวมสอบ")
    print("คะแนนรวมที่ได้\n", (Avg))
    print("ควรปรับปรุง")
elif Avg < 80:
    print("ผลคะแนนรวมสอบ")
    print("คะแนนรวมที่ได้\n", (Avg))
    print("ผ่าน")
else:
    print("ผลคะแนนรวมสอบ")
    print("คะแนนรวมที่ได้\n", (Avg))
    print("ดี่เยี่ยม")

print