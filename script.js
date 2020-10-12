var z=document.getElementById('result');
var x=document.getElementById('c1');
var y=document.getElementById('c2');
var element=document.getElementById("body");
function gradient(){
	element.style.background="linear-gradient(to bottom right ,"
	+x.value
	+","
	+y.value
	+") no-repeat center center fixed";
	result.textContent=element.style.background;
}
x.addEventListener("input",gradient);
y.addEventListener("input",gradient);