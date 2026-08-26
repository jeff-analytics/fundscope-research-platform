from app.manager_index import surname_initial,manager_id

def test_manager_initials():
    assert surname_initial('陈雪玲')=='C'
    assert surname_initial('WANG AO')=='W'
    assert surname_initial('方正')=='F'
    assert len(manager_id('陈雪玲','红土创新基金'))==16
