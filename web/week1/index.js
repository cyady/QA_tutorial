const express = require('express')
const app = express()
const port = 3000

app.get('/', function (req, res) {
    res.send('Hello World')
})
// HTTP메소드 요청의 목적, 종류를 알려주기위해 사용하는 수단
// get - 주소창을 통해 데이터 전달 , params query 두가지 방법이 있다.
// Post - 주소창이 아니라 내부적으로 body에 데이터 전달|
// Routing /뒷내용, /about , /about/board 등등
// 콜백함수(callback) : 함수가 끝나고 실행할 함수
// ex) setTimeout(()=>{console.log("1초지남")}, 1000) : 1000ms후에 {}를 실행해라

app.get('/cat', function (req, res) {
    res.send("<a href='https://www.youtube.com/watch?v=FKnzS_icp20'>고양이")
})

app.get('/dog', function (req, res) {
    res.send('<h1>강아지</h1>')
})

app.get('/tiger', function (req, res) {
    res.json({ 'sound': '어흥' })
    //res.send({ 'sound': '어흥' })도 가능
})

app.get('/user/:id', (req, res) => {
    // const q = req.params
    // console.log(q.id)
    const q = req.query
    console.log(q)

    res.json({'userid':q.name})
})

app.get('/sound/:name', (req, res) => {
    const {name} = req.params

    if(name =="dog") {
        res.json({'sound':'멍멍'})
    }
    else if(name =="cat") {
        res.json({'sound':'야옹'})
    }
    else if(name =="pig") {
        res.json({'sound':'꿀꿀'})
    }
    else {
        res.json({'sound':'알수없음'})
    }
})


app.listen(port, () => {
    console.log(`Example app listening on port ${port}`)
})
//3000은 포트번호이다.
//포트는 규격이 있다.검색하면 나온다. ex) HTTP-80(TCP), HTTPS-443(TCP) 등
//서버에서 listen하고 있어야 포트를 통해 연결이 가능

//backtick `을 사용해야 탬플릿 문자열을 활용할 수 있음
//그냥 출력할 때는 '', ""사용
