name = input("ชื่อเล่นของคุณคือ? ")
age = int(input("อายุของคุณ? "))
height = float(input("ส่วนสูง (ซม.)? "))
print("สวัสดี", name)
print("คุณอายุ", age, "ปี")
print("ส่วนสูง", height, "เซนติเมตร")

a = 12
b = 5.5
c = "Python"
print(a + b)
print(a * b)
print(c * 3)

people = 4
price = 850
room = 2400
print("จำนวนคน", people)
print("ราคาตั๋วต่อคน", price)
print("ค่าที่พักต่อห้อง", room)
print("ค่าใช้จ่ายทั้งหมด",people * price + room)
print("สนุกกับการท่องเที่ยว!")

people = int(input("จำนวนคน: "))
price = int(input("ราคาตั๋วต่อคน: "))
room = int(input("ค่าที่พักต่อหลัง: "))
total = people * price + room
print("ค่าใช้จ่ายทั้งหมด =", total)
print("สนุกกับการท่องเที่ยว!")