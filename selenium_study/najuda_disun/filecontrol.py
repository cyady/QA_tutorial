import os
import olefile

forder_path = r'C:\Users\cyady\Downloads\\'
print(forder_path)
each_file_path_and_gen_t = []
for each_file_name in os.listdir(forder_path):
    print(each_file_name)
    each_file_path = forder_path+each_file_name
    each_file_gen_time = os.path.getctime(each_file_path)
    # getctime: 입력받은 경로에 대한 생성 시간을 리턴
    each_file_path_and_gen_t.append(
        (each_file_path, each_file_gen_time)
    )
# 가장 생성시각이 큰(가장 최근인) 파일을 리턴
most_recent_file = max(each_file_path_and_gen_t, key=lambda x : x[1])[0]
print(most_recent_file + "\n")

f=olefile.OleFileIO(most_recent_file)
encoded_text = f.openstream('PrvText').read()
decoded_text = encoded_text.decode('UTF-16')
print(decoded_text)
# 데이터를 끝까지 출력하지 않는 문제를 발견함, 링버퍼를 활용해서 해결할 예정





