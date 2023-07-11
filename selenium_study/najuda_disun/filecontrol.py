import os
import olefile
import pandas as pd

class RingBuffer:
    def __init__(self, capacity):
        self.capacity = capacity
        self.buffer = [None] * capacity
        self.size = 0
        self.start = 0

    def is_empty(self):
        return self.size ==0

    def is_full(self):
        return self.size == self.capacity

    def enqueue(self, item):
        if self.is_full():
            self.start = (self.start + 1) % self.capacity
        else:
            self.size += 1

        self.buffer[(self.start + self.size -1 ) % self.capacity] = item

    def dequeue(self):
        if self.is_empty():
            raise Exception("Buffer is empty")

        item = self.buffer[self.start]
        self.buffer[self.start] = None
        self.start = (self.start + 1) % self.capacity
        self.size -= 1

        return item

    def peek(self):
        if self.is_empty():
            raise Exception("Buffer is empty")

        return self.buffer[self.start]

    def __len__(self):
        return self.size


def process_decoded_text(decoded_text, rows):
    buffer_size = rows  # 버퍼 크기를 행 개수로 설정
    buffer = RingBuffer(buffer_size)
    data = []

    for char in decoded_text:
        buffer.enqueue(char)
        if char == '\n':
            row = ''.join(c for c in buffer.buffer if c is not None)
            row = row.replace('\n', '')
            row = row.replace('<>', '\n')
            data.append(row.split("<>"))
            buffer = RingBuffer(buffer_size)

    return data

def file_select():
    forder_path = r'C:\Users\cyady\Downloads\\'
    print("find in here : ", forder_path)
    each_file_path_and_gen_t = []
    for each_file_name in os.listdir(forder_path):
        # print(each_file_name)
        each_file_path = forder_path + each_file_name
        each_file_gen_time = os.path.getctime(each_file_path)
        # getctime: 입력받은 경로에 대한 생성 시간을 리턴
        each_file_path_and_gen_t.append(
            (each_file_path, each_file_gen_time)
        )
    # 가장 생성시각이 큰(가장 최근인) 파일을 리턴
    most_recent_file = max(each_file_path_and_gen_t, key=lambda x: x[1])[0]
    print(most_recent_file + "\n")
    return most_recent_file

most_recent_file = file_select()    #파일 경로 설정

num_rows = 100    #행 개수 설정

f = olefile.OleFileIO(most_recent_file)
encoded_text = f.openstream('PrvText').read()
decoded_text = encoded_text.decode('UTF-16')

print(decoded_text)

data = process_decoded_text(decoded_text, num_rows)

df = pd.DataFrame(data)
output_filename = '7.6.xlsx'
df.to_excel(output_filename, index=False)

df.head()
df.tail(20)


#
# f=olefile.OleFileIO(most_recent_file)
# encoded_text = f.openstream('PrvText').read()
# decoded_text = encoded_text.decode('UTF-16')
# print(decoded_text)
# # 데이터를 끝까지 출력하지 않는 문제를 발견함, 링버퍼를 활용해서 해결할 예정





