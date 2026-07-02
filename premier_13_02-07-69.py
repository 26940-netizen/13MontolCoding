import random

Num = random.randint(1 , 100)

print("โปรแกรมทายเลขครับ สู้เขาลูกพวกลิง")
print("----------------------------------------------------------")

while True:
    P_Num = int(input("ตัวเลข :"))

    if Num < P_Num:
        print("เลขมากไปจรั๊ฟ พวกลิง")

    elif Num == P_Num:
        print("ถูกต้องค้าบเบ้บบบ เก่งมากกกก")

    else:
        print("เลขน้อยไปจ้าาา พวกลิง")

        