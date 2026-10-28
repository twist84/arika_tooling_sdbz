// Render the delivered HTML's actual JavaScript with a real Canvas backend.
// Requires @napi-rs/canvas. DOM/layout and browser download behavior are not emulated.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const {createCanvas,Image}=require('@napi-rs/canvas');
async function main()
{
    const path=process.argv[2];if(!path)throw Error('usage: node validate_menu_textured.js preview.html [screenshot.png]');
    const html=fs.readFileSync(path,'utf8'),script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
    const elements={};
    for(const id of [...html.matchAll(/id="([^"]+)"/g)].map(m=>m[1]))
        elements[id]={value:'',selectedIndex:0,checked:['background','motion','tint','first','middle','overlay','label_motion','arrows','character_motion','idle_motion'].includes(id),addEventListener(){},append(){}};
    elements.screen=createCanvas(512,448);elements.view.value='composite';elements.time.value='70';elements.atlas.value='0';
    const document={getElementById:id=>elements[id],querySelectorAll:()=>Object.values(elements).filter(e=>e.addEventListener),createElement:()=>({click(){}})};
    const context=vm.createContext({document,window:{},Image,console,requestAnimationFrame(){}});
    vm.runInContext(script,context);
    for(let i=0;i<500&&!context.window.menu_lab_ready;i++)await new Promise(resolve=>setTimeout(resolve,10));
    assert(context.window.menu_lab_ready,'textures did not load');
    const data=context.window.menu_lab.data;assert.equal(data.textures.length,13);assert.equal(data.items.length,7);
    function occupied(){const a=elements.screen.getContext('2d').getImageData(0,0,512,448).data;let n=0;for(let i=3;i<a.length;i+=4)if(a[i])n++;return n;}
    for(let item=0;item<7;item++){elements.item.selectedIndex=item;context.window.menu_lab.render();assert(occupied()>100000,'empty item '+item)}
    elements.item.selectedIndex=0;context.window.menu_lab.render();
    if(process.argv[3])fs.writeFileSync(process.argv[3],elements.screen.toBuffer('image/png'));
    elements.view.value='atlas';
    for(let i=0;i<13;i++){elements.atlas.value=String(i);context.window.menu_lab.render();assert(occupied()>0,'empty atlas '+i)}
    elements.view.value='shared';elements.time.value='0';context.window.menu_lab.render();assert(occupied()>0);
    elements.time.value='139';context.window.menu_lab.render();assert(occupied()>0);
    elements.view.value='item';for(const id of ['first','middle','overlay','arrows'])elements[id].checked=false;
    context.window.menu_lab.render();assert.equal(occupied(),0,'layer toggles');
    elements.overlay.checked=true;elements.time.value='70';context.window.menu_lab.render();assert(occupied()>0,'settled label');
    elements.time.value='139';context.window.menu_lab.render();assert.equal(occupied(),0,'exited label');
    elements.overlay.checked=false;elements.middle.checked=true;elements.time.value='70';context.window.menu_lab.render();assert(occupied()>0,'settled character');
    const with_idle=elements.screen.toBuffer('image/png');elements.idle_motion.checked=false;context.window.menu_lab.render();assert(!with_idle.equals(elements.screen.toBuffer('image/png')),'idle toggle made no visual change');elements.idle_motion.checked=true;
    elements.item.selectedIndex=5;elements.time.value='35';context.window.menu_lab.render();const customize_idle=elements.screen.toBuffer('image/png');elements.idle_motion.checked=false;context.window.menu_lab.render();assert(!customize_idle.equals(elements.screen.toBuffer('image/png')),'CUSTOMIZE idle toggle made no visual change');elements.idle_motion.checked=true;elements.item.selectedIndex=0;
    elements.item.selectedIndex=2;elements.time.value='70';context.window.menu_lab.render();const versus_idle=elements.screen.toBuffer('image/png');elements.idle_motion.checked=false;context.window.menu_lab.render();assert(!versus_idle.equals(elements.screen.toBuffer('image/png')),'VERSUS idle toggle made no visual change');elements.idle_motion.checked=true;elements.item.selectedIndex=0;
    elements.item.selectedIndex=6;elements.time.value='70';context.window.menu_lab.render();const options_idle=elements.screen.toBuffer('image/png');elements.idle_motion.checked=false;context.window.menu_lab.render();assert(!options_idle.equals(elements.screen.toBuffer('image/png')),'OPTIONS idle toggle made no visual change');elements.idle_motion.checked=true;elements.item.selectedIndex=0;
    elements.item.selectedIndex=3;elements.time.value='70';context.window.menu_lab.render();const dragon_idle=elements.screen.toBuffer('image/png');elements.idle_motion.checked=false;context.window.menu_lab.render();assert(!dragon_idle.equals(elements.screen.toBuffer('image/png')),'DRAGON SUMMONING idle toggle made no visual change');elements.idle_motion.checked=true;elements.item.selectedIndex=0;
    elements.time.value='139';context.window.menu_lab.render();assert.equal(occupied(),0,'exited character');elements.middle.checked=false;
    // The selected ORIGINAL scenery includes its sky strip, not the panels below it.
    elements.overlay.checked=false;elements.first.checked=true;elements.time.value='70';context.window.menu_lab.render();
    const sky=elements.screen.getContext('2d').getImageData(180,2,1,1).data;assert.equal(sky[3],255,'selected sky strip missing');
    assert(data.frames[70].strips[0].length>0,'ORIGINAL strip commands missing');
    elements.first.checked=false;elements.middle.checked=true;elements.overlay.checked=true;
    elements.shake.onclick();assert.equal(elements.time.value,80);assert(elements.emphasis.checked,'shake button did not enable demo');elements.play.onclick();
    elements.time.value='82';context.window.menu_lab.render();const shake_pixels=elements.screen.toBuffer('image/png');
    elements.emphasis.checked=false;context.window.menu_lab.render();assert(!shake_pixels.equals(elements.screen.toBuffer('image/png')),'shake demo made no visual change');
    elements.middle.checked=false;elements.overlay.checked=false;
    // Pixel-exact UV reversal and affine placement through the actual sprite function.
    const fixture=createCanvas(2,2),c=fixture.getContext('2d');
    c.fillStyle='#ff0000';c.fillRect(0,0,1,1);c.fillStyle='#00ff00';c.fillRect(1,0,1,1);
    c.fillStyle='#0000ff';c.fillRect(0,1,1,1);c.fillStyle='#ffffff';c.fillRect(1,1,1,1);
    context.fixture=fixture;
    vm.runInContext("images[0]=fixture;ctx.clearRect(0,0,512,448);sprite(0,{uv_endpoints:[2,2,0,0],vertices:[[0,0],[2,0],[0,2],[2,2]]})",context);
    const pixels=elements.screen.getContext('2d').getImageData(0,0,2,2).data;
    assert.deepEqual([...pixels],[255,255,255,255,0,0,255,255,0,255,0,255,255,0,0,255]);
    // Queue order must not bury high-depth sprites below later low-depth sprites.
    vm.runInContext("ctx.clearRect(0,0,512,448);draw_queue=[];enqueue(0,{depth:10,uv_endpoints:[0,0,1,1],vertices:[[0,0],[4,0],[0,4],[4,4]]},0);enqueue(0,{depth:5,uv_endpoints:[0,1,1,2],vertices:[[0,0],[4,0],[0,4],[4,4]]},0);flush()",context);
    assert.deepEqual([...elements.screen.getContext('2d').getImageData(1,1,1,1).data],[255,0,0,255]);
    console.log('Passed: 13 atlases, seven items, shared timeline endpoints, layer isolation and pixel-exact reversed UV placement.');
}
main().catch(e=>{console.error(e);process.exitCode=1});
