// 页面加载完成后执行
document.addEventListener('DOMContentLoaded', function() {
    // 平滑滚动导航
    initSmoothScroll();
    
    // FAQ 折叠功能
    initFAQ();
    
    // 导航栏滚动效果
    initNavbarScroll();
    
    // 动画效果
    initAnimations();
    
    // 联系我们弹窗
    initContactModal();
    
    // 滚动动画
    initScrollAnimations();
    
    // 数字计数动画
    initCounterAnimations();

});

    // 为登录按钮添加点击事件
    document.addEventListener('DOMContentLoaded', function() {
        const loginButton = document.querySelector('.btn-login');
        const loginButton1 = document.querySelector('.btn-login1');

        if (loginButton) {
            loginButton.addEventListener('click', function() {
                window.location.href = '${BASE_URL}/app/';
            });
        }

        if (loginButton1) {
            loginButton1.addEventListener('click', function() {
                window.location.href = '${BASE_URL}/app/';
            });
        }
    });


// 平滑滚动导航
function initSmoothScroll() {
    const navLinks = document.querySelectorAll('.nav-link');
    
    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            
            const targetId = this.getAttribute('href');
            const targetSection = document.querySelector(targetId);
            
            if (targetSection) {
                const offsetTop = targetSection.offsetTop - 100; // 考虑固定导航栏高度
                
                window.scrollTo({
                    top: offsetTop,
                    behavior: 'smooth'
                });
                
                // 添加点击反馈效果
                this.style.transform = 'scale(0.95)';
                setTimeout(() => {
                    this.style.transform = '';
                }, 150);
            }
        });
    });
}

// FAQ 折叠功能
function initFAQ() {
    const faqItems = document.querySelectorAll('.faq-item');
    
    faqItems.forEach(item => {
        const question = item.querySelector('.faq-question');
        
        question.addEventListener('click', function() {
            const isActive = item.classList.contains('active');
            
            // 关闭所有其他 FAQ 项目
            faqItems.forEach(otherItem => {
                if (otherItem !== item) {
                    otherItem.classList.remove('active');
                }
            });
            
            // 切换当前项目
            if (isActive) {
                item.classList.remove('active');
            } else {
                item.classList.add('active');
            }
        });
    });
}

// 导航栏滚动效果
function initNavbarScroll() {
    const navbar = document.querySelector('.navbar');
    let lastScrollTop = 0;
    
    window.addEventListener('scroll', function() {
        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
        
        if (scrollTop > 100) {
            navbar.style.background = 'rgba(255, 255, 255, 0.95)';
            navbar.style.backdropFilter = 'blur(10px)';
        } else {
            navbar.style.background = '#ffffff';
            navbar.style.backdropFilter = 'none';
        }
        
        lastScrollTop = scrollTop;
    });
}

// 动画效果
function initAnimations() {
    // 创建 Intersection Observer 用于滚动动画
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };
    
    const observer = new IntersectionObserver(function(entries) {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
            }
        });
    }, observerOptions);
    
    // 观察需要动画的元素
    const animatedElements = document.querySelectorAll('.feature-card, .case-card, .opt-feature');
    
    animatedElements.forEach(element => {
        element.style.opacity = '0';
        element.style.transform = 'translateY(30px)';
        element.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
        observer.observe(element);
    });
}

// 按钮点击效果
document.addEventListener('click', function(e) {
    if (e.target.matches('.btn-primary, .btn-secondary, .btn-login')) {
        // 添加点击波纹效果
        const ripple = document.createElement('span');
        const rect = e.target.getBoundingClientRect();
        const size = Math.max(rect.width, rect.height);
        const x = e.clientX - rect.left - size / 2;
        const y = e.clientY - rect.top - size / 2;
        
        ripple.style.width = ripple.style.height = size + 'px';
        ripple.style.left = x + 'px';
        ripple.style.top = y + 'px';
        ripple.classList.add('ripple');
        
        e.target.appendChild(ripple);
        
        setTimeout(() => {
            ripple.remove();
        }, 600);
    }
});

// 添加波纹效果样式
const style = document.createElement('style');
style.textContent = `
    .btn-primary, .btn-secondary, .btn-login {
        position: relative;
        overflow: hidden;
    }
    
    .ripple {
        position: absolute;
        border-radius: 50%;
        background: rgba(255, 255, 255, 0.3);
        transform: scale(0);
        animation: ripple-animation 0.6s linear;
        pointer-events: none;
    }
    
    @keyframes ripple-animation {
        to {
            transform: scale(4);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

// 数字计数动画
function animateNumbers() {
    const numberElements = document.querySelectorAll('.stat-number, .metric-value');
    
    numberElements.forEach(element => {
        const target = parseInt(element.textContent.replace(/[^\d]/g, ''));
        if (isNaN(target)) return;
        
        const duration = 2000; // 2秒
        const increment = target / (duration / 16); // 60fps
        let current = 0;
        
        const timer = setInterval(() => {
            current += increment;
            if (current >= target) {
                current = target;
                clearInterval(timer);
            }
            
            // 保持原始格式
            const originalText = element.textContent;
            if (originalText.includes('%')) {
                element.textContent = Math.floor(current) + '%';
            } else if (originalText.includes('+')) {
                element.textContent = Math.floor(current) + '+';
            } else if (originalText.includes('x')) {
                element.textContent = Math.floor(current) + 'x';
            } else {
                element.textContent = Math.floor(current);
            }
        }, 16);
    });
}

// 当仪表盘预览进入视口时启动数字动画
const dashboardObserver = new IntersectionObserver(function(entries) {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            animateNumbers();
            dashboardObserver.unobserve(entry.target);
        }
    });
}, { threshold: 0.5 });

const dashboardPreview = document.querySelector('.dashboard-preview');
if (dashboardPreview) {
    dashboardObserver.observe(dashboardPreview);
}

// 表单验证（如果有表单的话）
function validateForm(form) {
    const inputs = form.querySelectorAll('input[required], textarea[required]');
    let isValid = true;
    
    inputs.forEach(input => {
        if (!input.value.trim()) {
            input.style.borderColor = 'rgb(70, 95, 255)';
            isValid = false;
        } else {
            input.style.borderColor = '#e0e0e0';
        }
    });
    
    return isValid;
}

// 添加键盘导航支持
document.addEventListener('keydown', function(e) {
    if (e.key === 'Tab') {
        document.body.classList.add('keyboard-navigation');
    }
});

document.addEventListener('mousedown', function() {
    document.body.classList.remove('keyboard-navigation');
});

// 添加键盘导航样式
const keyboardStyle = document.createElement('style');
keyboardStyle.textContent = `
    .keyboard-navigation *:focus {
        outline: 2px solid rgb(70, 95, 255) !important;
        outline-offset: 2px !important;
    }
`;
document.head.appendChild(keyboardStyle);

// 性能优化：防抖函数
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// 优化滚动事件
const optimizedScrollHandler = debounce(function() {
    // 滚动相关的处理逻辑
}, 16);

window.addEventListener('scroll', optimizedScrollHandler);

// 错误处理
window.addEventListener('error', function(e) {
    console.error('页面错误:', e.error);
});

// 页面可见性变化处理
document.addEventListener('visibilitychange', function() {
    if (document.hidden) {
        // 页面隐藏时的处理
        console.log('页面已隐藏');
    } else {
        // 页面显示时的处理
        console.log('页面已显示');
    }
});

// 联系我们弹窗功能
function initContactModal() {
    const modal = document.getElementById('contactModal');
    const contactTriggers = document.querySelectorAll('.contact-trigger');
    const closeBtn = document.querySelector('.modal-close');
    const copyButtons = document.querySelectorAll('.btn-copy');
    
    // 打开弹窗
    contactTriggers.forEach(trigger => {
        trigger.addEventListener('click', function(e) {
            e.preventDefault();
            modal.style.display = 'block';
            document.body.style.overflow = 'hidden'; // 防止背景滚动
        });
    });
    
    // 关闭弹窗
    function closeModal() {
        modal.style.display = 'none';
        document.body.style.overflow = 'auto';
    }
    
    closeBtn.addEventListener('click', closeModal);
    
    // 点击背景关闭弹窗
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            closeModal();
        }
    });
    
    // ESC键关闭弹窗
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && modal.style.display === 'block') {
            closeModal();
        }
    });
    
    // 复制功能
    copyButtons.forEach(button => {
        button.addEventListener('click', function() {
            const textToCopy = this.getAttribute('data-text');
            
            // 使用现代 Clipboard API
            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(textToCopy).then(() => {
                    showCopySuccess(this);
                }).catch(() => {
                    fallbackCopyText(textToCopy, this);
                });
            } else {
                fallbackCopyText(textToCopy, this);
            }
        });
    });
}

// 复制成功提示
function showCopySuccess(button) {
    const originalText = button.textContent;
    button.textContent = '已复制!';
    button.classList.add('copied');
    
    setTimeout(() => {
        button.textContent = originalText;
        button.classList.remove('copied');
    }, 2000);
}

// 备用复制方法
function fallbackCopyText(text, button) {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.left = '-999999px';
    textArea.style.top = '-999999px';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    
    try {
        document.execCommand('copy');
        showCopySuccess(button);
    } catch (err) {
        console.error('复制失败:', err);
        // 如果复制失败，可以显示一个提示
        alert('复制失败，请手动复制：' + text);
    } finally {
        document.body.removeChild(textArea);
    }
}

// 世界地图交互功能
function initWorldMap() {
    const continents = document.querySelectorAll('.continent');
    const tooltip = createTooltip();
    
    // 大洲数据
    const continentData = {
        '北美洲': { region: '北美', clients: '800+', growth: '28%', description: '北美市场覆盖美国、加拿大、墨西哥，服务800+企业，是Pulse AI的重要市场' },
        '南美洲': { region: '南美', clients: '200+', growth: '35%', description: '南美市场快速增长，覆盖巴西、阿根廷、智利等主要国家，服务200+企业' },
        '欧洲': { region: '欧洲', clients: '600+', growth: '30%', description: '欧洲市场稳定发展，覆盖英国、德国、法国等发达国家，服务600+企业' },
        '非洲': { region: '非洲', clients: '150+', growth: '40%', description: '非洲市场潜力巨大，覆盖南非、尼日利亚、埃及等主要国家，服务150+企业' },
        '亚洲': { region: '亚洲', clients: '1200+', growth: '32%', description: '亚洲总部所在地，覆盖中国、日本、印度、东南亚等，服务1200+企业' },
        '大洋洲': { region: '大洋洲', clients: '100+', growth: '25%', description: '大洋洲市场稳定发展，覆盖澳大利亚、新西兰等国家，服务100+企业' },
        '南极洲': { region: '南极', clients: '0', growth: '0%', description: '南极洲暂无业务覆盖，未来可考虑科研机构合作' }
    };
    
    continents.forEach(continent => {
        const continentName = continent.getAttribute('data-continent');
        const data = continentData[continentName];
        
        if (data) {
            // 鼠标悬停效果
            continent.addEventListener('mouseenter', function(e) {
                showTooltip(e, continentName, data);
                continent.style.transform = 'scale(1.02)';
                continent.style.zIndex = '10';
            });
            
            continent.addEventListener('mousemove', function(e) {
                updateTooltipPosition(e);
            });
            
            continent.addEventListener('mouseleave', function() {
                hideTooltip();
                continent.style.transform = 'scale(1)';
                continent.style.zIndex = '1';
            });
            
            // 点击效果
            continent.addEventListener('click', function() {
                showContinentDetails(continentName, data);
            });
        }
    });
    
    // 添加地图动画
    animateMapElements();
}

// 创建工具提示
function createTooltip() {
    const tooltip = document.createElement('div');
    tooltip.className = 'map-tooltip';
    tooltip.style.cssText = `
        position: absolute;
        background: rgba(0, 0, 0, 0.9);
        color: white;
        padding: 12px 16px;
        border-radius: 8px;
        font-size: 14px;
        font-weight: 500;
        pointer-events: none;
        z-index: 1000;
        opacity: 0;
        transform: translateY(10px);
        transition: all 0.3s ease;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.2);
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        max-width: 250px;
    `;
    document.body.appendChild(tooltip);
    return tooltip;
}

// 显示工具提示
function showTooltip(e, continentName, data) {
    const tooltip = document.querySelector('.map-tooltip');
    tooltip.innerHTML = `
        <div style="font-weight: 600; margin-bottom: 4px; color: rgb(70, 95, 255);">${continentName}</div>
        <div style="font-size: 12px; margin-bottom: 6px; opacity: 0.8;">${data.region}</div>
        <div style="font-size: 12px; margin-bottom: 2px;">客户数量: <span style="color: rgb(70, 95, 255);">${data.clients}</span></div>
        <div style="font-size: 12px;">增长率: <span style="color: #28a745;">${data.growth}</span></div>
    `;
    
    updateTooltipPosition(e);
    tooltip.style.opacity = '1';
    tooltip.style.transform = 'translateY(0)';
}

// 更新工具提示位置
function updateTooltipPosition(e) {
    const tooltip = document.querySelector('.map-tooltip');
    const x = e.clientX + 10;
    const y = e.clientY - 10;
    
    tooltip.style.left = x + 'px';
    tooltip.style.top = y + 'px';
}

// 隐藏工具提示
function hideTooltip() {
    const tooltip = document.querySelector('.map-tooltip');
    tooltip.style.opacity = '0';
    tooltip.style.transform = 'translateY(10px)';
}

// 显示大洲详情
function showContinentDetails(continentName, data) {
    // 创建详情弹窗
    const modal = document.createElement('div');
    modal.className = 'country-modal';
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.5);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 2000;
        backdrop-filter: blur(5px);
        animation: fadeIn 0.3s ease;
    `;
    
    modal.innerHTML = `
        <div style="
            background: white;
            border-radius: 16px;
            padding: 32px;
            max-width: 500px;
            width: 90%;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            animation: slideIn 0.3s ease;
            position: relative;
        ">
            <button class="modal-close" style="
                position: absolute;
                top: 16px;
                right: 16px;
                background: none;
                border: none;
                font-size: 24px;
                cursor: pointer;
                color: #666;
                width: 32px;
                height: 32px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: 50%;
                transition: all 0.3s ease;
            ">&times;</button>
            
            <div style="margin-bottom: 24px;">
                <h2 style="
                    font-size: 28px;
                    font-weight: 700;
                    color: #1a1a1a;
                    margin: 0 0 8px 0;
                    background: linear-gradient(135deg, rgb(70, 95, 255), rgb(50, 75, 235));
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                    background-clip: text;
                ">${continentName}</h2>
                <div style="
                    background: rgb(70, 95, 255);
                    color: white;
                    padding: 4px 12px;
                    border-radius: 20px;
                    font-size: 14px;
                    font-weight: 500;
                    display: inline-block;
                ">${data.region}</div>
            </div>
            
            <div style="margin-bottom: 24px;">
                <p style="color: #666; line-height: 1.6; margin: 0;">${data.description}</p>
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 24px;">
                <div style="text-align: center; padding: 20px; background: #f8f9fa; border-radius: 12px;">
                    <div style="font-size: 24px; font-weight: 700; color: rgb(70, 95, 255); margin-bottom: 4px;">${data.clients}</div>
                    <div style="font-size: 14px; color: #666;">客户数量</div>
                </div>
                <div style="text-align: center; padding: 20px; background: #f8f9fa; border-radius: 12px;">
                    <div style="font-size: 24px; font-weight: 700; color: #28a745; margin-bottom: 4px;">${data.growth}</div>
                    <div style="font-size: 14px; color: #666;">增长率</div>
                </div>
            </div>
            
            <div style="text-align: center;">
                <button class="btn-primary" style="
                    background: rgb(70, 95, 255);
                    color: white;
                    border: none;
                    padding: 12px 24px;
                    border-radius: 8px;
                    font-weight: 600;
                    cursor: pointer;
                    transition: all 0.3s ease;
                ">了解详情</button>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    document.body.style.overflow = 'hidden';
    
    // 关闭弹窗
    const closeBtn = modal.querySelector('.modal-close');
    closeBtn.addEventListener('click', () => {
        document.body.removeChild(modal);
        document.body.style.overflow = 'auto';
    });
    
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            document.body.removeChild(modal);
            document.body.style.overflow = 'auto';
        }
    });
    
    // 添加按钮悬停效果
    const btn = modal.querySelector('.btn-primary');
    btn.addEventListener('mouseenter', () => {
        btn.style.background = 'rgb(50, 75, 235)';
        btn.style.transform = 'translateY(-2px)';
    });
    
    btn.addEventListener('mouseleave', () => {
        btn.style.background = 'rgb(70, 95, 255)';
        btn.style.transform = 'translateY(0)';
    });
}

// 地图元素动画
function animateMapElements() {
    const continents = document.querySelectorAll('.continent');
    const connections = document.querySelectorAll('.connections line');
    const pulsePoints = document.querySelectorAll('.pulse-point');
    
    // 大洲动画
    continents.forEach((continent, index) => {
        continent.style.opacity = '0';
        continent.style.transform = 'scale(0.8)';
        continent.style.transition = 'all 0.6s ease';
        
        setTimeout(() => {
            continent.style.opacity = '1';
            continent.style.transform = 'scale(1)';
        }, index * 200);
    });
    
    // 连接线动画
    connections.forEach((line, index) => {
        line.style.opacity = '0';
        line.style.strokeDasharray = '0 1000';
        line.style.transition = 'all 1s ease';
        
        setTimeout(() => {
            line.style.opacity = '0.7';
            line.style.strokeDasharray = '5,5';
        }, 1000 + index * 300);
    });
    
    // 脉冲点动画
    pulsePoints.forEach((point, index) => {
        point.style.opacity = '0';
        point.style.transform = 'scale(0)';
        point.style.transition = 'all 0.8s ease';
        
        setTimeout(() => {
            point.style.opacity = '1';
            point.style.transform = 'scale(1)';
        }, 1500 + index * 400);
    });
}

// 滚动动画
function initScrollAnimations() {
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };
    
    const observer = new IntersectionObserver(function(entries) {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('animate-in');
                
                // 为功能卡片添加延迟动画
                if (entry.target.classList.contains('feature-card')) {
                    const cards = entry.target.parentElement.querySelectorAll('.feature-card');
                    cards.forEach((card, index) => {
                        setTimeout(() => {
                            card.style.opacity = '1';
                            card.style.transform = 'translateY(0)';
                        }, index * 100);
                    });
                }
                
                // 为平台卡片添加延迟动画
                if (entry.target.classList.contains('platform-card')) {
                    const cards = entry.target.parentElement.querySelectorAll('.platform-card');
                    cards.forEach((card, index) => {
                        setTimeout(() => {
                            card.style.opacity = '1';
                            card.style.transform = 'translateY(0)';
                        }, index * 150);
                    });
                }
                
                // 为其他动画元素添加立即动画
                if (!entry.target.classList.contains('feature-card') && !entry.target.classList.contains('platform-card')) {
                    entry.target.style.opacity = '1';
                    entry.target.style.transform = 'translateY(0)';
                }
            }
        });
    }, observerOptions);
    
    // 观察需要动画的元素
    const animatedElements = document.querySelectorAll('.feature-card, .case-card, .hero-stat, .platform-card');
    
    animatedElements.forEach(element => {
        element.style.opacity = '0';
        element.style.transform = 'translateY(30px)';
        element.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
        observer.observe(element);
    });
}

// 数字计数动画
function initCounterAnimations() {
    const counterElements = document.querySelectorAll('.stat-number, .metric-value');
    
    const counterObserver = new IntersectionObserver(function(entries) {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                animateCounter(entry.target);
                counterObserver.unobserve(entry.target);
            }
        });
    }, { threshold: 0.5 });
    
    counterElements.forEach(element => {
        counterObserver.observe(element);
    });
}

// 数字计数动画函数
function animateCounter(element) {
    const target = parseInt(element.textContent.replace(/[^\d]/g, ''));
    if (isNaN(target)) return;
    
    const duration = 2000;
    const increment = target / (duration / 16);
    let current = 0;
    
    const timer = setInterval(() => {
        current += increment;
        if (current >= target) {
            current = target;
            clearInterval(timer);
        }
        
        // 保持原始格式
        const originalText = element.textContent;
        if (originalText.includes('%')) {
            element.textContent = Math.floor(current) + '%';
        } else if (originalText.includes('+')) {
            element.textContent = Math.floor(current) + '+';
        } else if (originalText.includes('x')) {
            element.textContent = Math.floor(current) + 'x';
        } else if (originalText.includes(',')) {
            element.textContent = Math.floor(current).toLocaleString();
        } else {
            element.textContent = Math.floor(current);
        }
    }, 16);
}

// 增强的按钮交互效果
function initEnhancedButtons() {
    const buttons = document.querySelectorAll('.btn-primary, .btn-secondary, .btn-login');
    
    buttons.forEach(button => {
        button.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-2px) scale(1.02)';
        });
        
        button.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0) scale(1)';
        });
        
        button.addEventListener('mousedown', function() {
            this.style.transform = 'translateY(0) scale(0.98)';
        });
        
        button.addEventListener('mouseup', function() {
            this.style.transform = 'translateY(-2px) scale(1.02)';
        });
    });
}

// 卡片悬停效果
function initCardHoverEffects() {
    const cards = document.querySelectorAll('.feature-card, .case-card, .platform-card');
    
    cards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-8px) scale(1.02)';
        });
        
        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0) scale(1)';
        });
    });
}

// 页面加载完成后初始化增强功能
document.addEventListener('DOMContentLoaded', function() {
    initEnhancedButtons();
    initCardHoverEffects();
    
    // 确保控制台内容可见
    setTimeout(() => {
        const platformCards = document.querySelectorAll('.platform-card');
        platformCards.forEach(card => {
            if (card.style.opacity === '0' || !card.style.opacity) {
                card.style.opacity = '1';
                card.style.transform = 'translateY(0)';
            }
        });
    }, 1000);
});

// 导出函数供全局使用
window.PulseAI = {
    validateForm,
    animateNumbers,
    showContactModal: function() {
        const modal = document.getElementById('contactModal');
        modal.style.display = 'block';
        document.body.style.overflow = 'hidden';
    },
    initScrollAnimations,
    initCounterAnimations
};
