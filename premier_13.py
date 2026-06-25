print ("โปรแกรมคำนวณค่า BMI และแปลผลสุขภาพ")

weight = int(input("น้ำหนักของตนเอง"))

height = float(input("ส่วนสูงของตนเอง (หน่วยเมตร)"))

BMI = weight / (height * height)

print (BMI)

if BMI < 18.5 :
    print("น้ำหนักน้อย กินข้าวบ้างนะ")
elif BMI <= 22.9 :
    print("ปกติ สเต็กเลย")
elif BMI <= 24.9 :
    print("น้ำหนักเกิน ลดการกินหน่อยนะ")
else :
    print("อ้วน ลดน้ำหนักด้วย")